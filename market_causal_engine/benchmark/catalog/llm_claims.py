"""Event-level LLM causal claim extraction for catalog EDGAR feed."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from market_causal_engine.benchmark.catalog.claim_quality import (
    enrich_extracted_claim,
    is_generic_effect,
    prune_stored_claims,
)
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.atom_scorer import score_claim
from market_causal_engine.extraction.causal_claim_extractor import extract_claims_from_atom
from market_causal_engine.extraction.llm_config import LLMConfig
from market_causal_engine.extraction.llm_extractor import _claim_polarity_from_text
from market_causal_engine.extraction.rule_validator import normalize_claim, validate_claim
from market_causal_engine.lookahead import LookAheadPolicy

MAX_ATOMS_IN_PROMPT = 8
MAX_ATOM_CHARS = 900
_EARNINGS_HINTS = (
    "earnings",
    "revenue",
    "eps",
    "guidance",
    "subscriber",
    "margin",
    "beat",
    "miss",
    "outlook",
    "forecast",
)


def _atom_signal(atom: MarketAtom) -> int:
    text = atom.text.lower()
    return sum(1 for hint in _EARNINGS_HINTS if hint in text)


def _atom_excerpt(atom: MarketAtom) -> str:
    text = atom.text.strip().replace("\n", " ")
    if len(text) > MAX_ATOM_CHARS:
        return text[:MAX_ATOM_CHARS] + "..."
    return text


def _build_event_prompt(
    atoms: list[MarketAtom],
    *,
    domain: str,
    ticker: str,
    event_date: str,
) -> str:
    atom_blocks = []
    for atom in atoms[:MAX_ATOMS_IN_PROMPT]:
        atom_blocks.append(
            {
                "atom_id": atom.atom_id,
                "published_at": atom.effective_time(),
                "tags": list(atom.tags or []),
                "text": _atom_excerpt(atom),
            }
        )

    return f"""Extract causal market claims from pre-earnings EDGAR evidence atoms.

Domain: {domain}
Ticker: {ticker}
Event date: {event_date}

Return ONLY a JSON array (no markdown). Each claim object must include:
- cause (short string: the disclosed fact, e.g. "Q1 revenue beat by 8%")
- effect (short string: the market mechanism, NOT stock direction — see examples)
- mechanism (one of: fundamental, sentiment, liquidity, macro, regulatory, trust)
- severity (0.0-1.0)
- polarity (-1.0 bearish, 0.0 neutral, 1.0 bullish for next-day stock direction)
- evidence_span (exact substring copied from the source atom text, >= 20 chars)
- source_id (must match an atom_id below)
- published_at (integer minute from source atom)

Effect field rules (CRITICAL):
- Describe HOW the filing moves estimates/valuations, not "stock goes up/down".
- Include a concrete metric or mechanism when visible in evidence (revenue, EPS, margin, guidance, subscribers).
- GOOD effects: "estimate revision upside", "margin compression concern", "guidance cut lowers FY outlook", "subscriber miss breaks growth narrative"
- BAD effects (do NOT use): "positive next-day stock direction", "bullish reaction", "price sensitivity", "upside pressure"

Other rules:
- Use only information visible in the atom texts (no post-earnings price labels).
- Prefer earnings beat/miss, guidance changes, revenue/EPS surprises, margin shifts.
- Skip generic legal boilerplate and forward-looking statement disclaimers.
- Return 2-4 high-signal claims; use |polarity| >= 0.5 when direction is clear, >= 0.25 when moderate.
- polarity sign MUST match the evidence_span tone (beat/growth -> positive, miss/cut/loss -> negative).

Atoms:
{json.dumps(atom_blocks, ensure_ascii=False, indent=2)}
"""


def _call_llm(prompt: str, config: LLMConfig, *, retries: int = 5) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "model": config.model,
            "messages": [
                {"role": "system", "content": "Respond with valid JSON only. No markdown fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{config.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content.rsplit("```", 1)[0]
                content = content.strip()
            raw = json.loads(content)
            if isinstance(raw, list):
                return raw
            if isinstance(raw, dict) and isinstance(raw.get("claims"), list):
                return raw["claims"]
            return [raw]
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    return []


def _atom_by_id(atoms: list[MarketAtom]) -> dict[str, MarketAtom]:
    return {atom.atom_id: atom for atom in atoms}


def _llm_atom_fallback(
    atoms: list[MarketAtom],
    *,
    domain: str,
    as_of: int,
    policy: LookAheadPolicy | None,
    case_prefix: str,
    max_atoms: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    idx = 0
    for atom in atoms[:max_atoms]:
        batch_ok, batch_rej = extract_claims_from_atom(
            atom,
            domain=domain,
            as_of=as_of,
            policy=policy,
            use_llm=True,
            claim_index=idx,
            case_prefix=case_prefix,
        )
        for claim in batch_ok:
            if "polarity" not in claim:
                claim["polarity"] = round(
                    _claim_polarity_from_text(
                        f"{claim.get('cause', '')} {claim.get('effect', '')} {claim.get('evidence_span', '')}"
                    ),
                    3,
                )
        accepted.extend(batch_ok)
        rejected.extend(batch_rej)
        idx += len(batch_ok)
    accepted = prune_stored_claims(accepted)
    return accepted, rejected


def _rank_atoms(atoms: list[MarketAtom]) -> list[MarketAtom]:
    return sorted(
        atoms,
        key=lambda atom: (_atom_signal(atom), atom.effective_time()),
        reverse=True,
    )


def _process_event_proposals(
    proposals: list[dict[str, Any]],
    atoms: list[MarketAtom],
    *,
    domain: str,
    as_of: int,
    policy: LookAheadPolicy | None,
    case_prefix: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    atoms_map = _atom_by_id(atoms)
    idx = 0

    for proposal in proposals:
        atom = atoms_map.get(str(proposal.get("source_id", "")))
        if atom is None:
            rejected.append({**proposal, "validation": {"passed": False, "errors": ["unknown_source_id"]}})
            continue
        claim = normalize_claim(proposal, atom)
        if is_generic_effect(str(claim.get("effect", ""))):
            rejected.append(
                {
                    **claim,
                    "atom_id": atom.atom_id,
                    "validation": {"passed": False, "errors": ["generic_effect"]},
                    "proposer": "llm_event",
                }
            )
            continue
        if "polarity" not in claim:
            claim["polarity"] = round(
                _claim_polarity_from_text(
                    f"{claim.get('cause', '')} {claim.get('effect', '')} {claim.get('evidence_span', '')}"
                ),
                3,
            )
        validation = validate_claim(claim, atom, domain=domain, as_of=as_of, policy=policy)
        record = {
            **claim,
            "atom_id": atom.atom_id,
            "validation": validation.to_dict(),
            "proposer": "llm_event",
        }
        if validation.passed:
            record.update(score_claim(claim, atom))
            record = enrich_extracted_claim(record)
            record["claim_id"] = f"{case_prefix}_C{idx:03d}"
            accepted.append(record)
            idx += 1
        else:
            rejected.append(record)

    accepted = prune_stored_claims(accepted)
    proposer = "llm_event" if accepted else "llm_event_empty"
    return accepted, rejected, proposer


def extract_catalog_claims_llm(
    atoms: list[MarketAtom],
    *,
    domain: str,
    ticker: str,
    event_date: str,
    as_of: int,
    policy: LookAheadPolicy | None,
    case_prefix: str,
    config: LLMConfig,
) -> dict[str, Any]:
    if not config.enabled:
        raise RuntimeError("LLM API key not configured (OPENAI_API_KEY or ZHISUAN_API_KEY)")

    ranked = _rank_atoms(atoms)
    prompt = _build_event_prompt(ranked, domain=domain, ticker=ticker, event_date=event_date)
    proposals = _call_llm(prompt, config)
    if not proposals:
        proposals = _call_llm(prompt, config)

    accepted, rejected, proposer = _process_event_proposals(
        proposals,
        ranked,
        domain=domain,
        as_of=as_of,
        policy=policy,
        case_prefix=case_prefix,
    )

    if not accepted:
        fallback_ok, fallback_rej = _llm_atom_fallback(
            ranked,
            domain=domain,
            as_of=as_of,
            policy=policy,
            case_prefix=case_prefix,
        )
        accepted = fallback_ok
        rejected.extend(fallback_rej)
        proposer = "llm_atom_fallback" if accepted else "llm_atom_fallback_empty"

    return {
        "accepted": accepted,
        "rejected": rejected,
        "claim_count": len(accepted),
        "rejected_count": len(rejected),
        "llm_model": config.model,
        "llm_base_url": config.base_url,
        "llm_proposer": proposer,
    }

