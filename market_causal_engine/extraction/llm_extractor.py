"""Propose causal claims from atoms (heuristic default, optional LLM API)."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from market_causal_engine.analysis import MECHANISM_CATEGORIES
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.patterns import infer_severity, infer_tone

DOMAIN_DEFAULT_MECHANISM = {
    "earnings": "fundamental",
    "short_report": "trust",
    "macro": "macro",
}

CAUSE_EFFECT_HINTS: list[tuple[re.Pattern[str], str, str, str, float]] = [
    (
        re.compile(r"subscriber.{0,20}(?:loss|decline|miss)", re.I),
        "subscriber loss",
        "growth narrative break",
        "fundamental",
        -1.0,
    ),
    (
        re.compile(r"(?:guidance|outlook).{0,30}(?:cut|lower|reduced|weak)", re.I),
        "guidance reduction",
        "forward earnings revision",
        "fundamental",
        -1.0,
    ),
    (
        re.compile(r"(?:earnings|eps|revenue|membership).{0,30}(?:miss|below|shortfall|decline|loss|fell|decrease)", re.I),
        "earnings miss",
        "valuation de-rating",
        "fundamental",
        -1.0,
    ),
    (
        re.compile(r"(?:net\s+loss|operating\s+loss|loss\s+of\s+\d)", re.I),
        "reported loss",
        "profitability concern",
        "fundamental",
        -1.0,
    ),
    (
        re.compile(r"(?:beat|exceed|surpass).{0,30}(?:estimate|expectation|consensus|forecast)", re.I),
        "earnings beat",
        "positive revision momentum",
        "fundamental",
        1.0,
    ),
    (
        re.compile(r"(?:record|strong|solid).{0,20}(?:revenue|earnings|growth|profit)", re.I),
        "strong results",
        "estimate upside",
        "fundamental",
        1.0,
    ),
    (
        re.compile(r"(?:revenue|eps).{0,20}(?:growth|increase|rose|grew)", re.I),
        "revenue growth",
        "fundamental upside",
        "fundamental",
        1.0,
    ),
    (
        re.compile(r"(?:downgrade|lowered?\s+rating|price\s+target\s+cut)", re.I),
        "analyst downgrade",
        "sentiment deterioration",
        "sentiment",
        -1.0,
    ),
    (
        re.compile(r"(?:upgrade|raised?\s+rating|price\s+target\s+(?:raise|increase))", re.I),
        "analyst upgrade",
        "sentiment improvement",
        "sentiment",
        1.0,
    ),
    (
        re.compile(r"(?:short\s+seller|hindenburg|muddy\s+waters|fraud|fabricat)", re.I),
        "fraud allegations",
        "trust collapse",
        "trust",
        -1.0,
    ),
    (
        re.compile(r"(?:regulatory\s+probe|sec\s+investigation|under\s+investigation|subpoena|enforcement\s+action)", re.I),
        "regulatory scrutiny",
        "regulatory overhang",
        "regulatory",
        -0.5,
    ),
    (
        re.compile(r"(?:put\s+option|volatility\s+spike|gamma|liquidity)", re.I),
        "options/liquidity stress",
        "forced de-risking",
        "liquidity",
        -0.5,
    ),
    (
        re.compile(r"(?:fomc|rate\s+hike|hawkish|fed\s+decision)", re.I),
        "monetary policy shock",
        "risk appetite compression",
        "macro",
        -0.5,
    ),
    (
        re.compile(r"(?:cpi|inflation).{0,20}(?:hot|surprise|above)", re.I),
        "inflation surprise",
        "rate path repricing",
        "macro",
        -0.5,
    ),
    (
        re.compile(r"(?:reddit|wallstreetbets|short\s+squeeze|retail)", re.I),
        "retail coordination",
        "short-covering pressure",
        "sentiment",
        1.0,
    ),
    (
        re.compile(r"(?:sector\s+etf|beta|spillover|rotation)", re.I),
        "sector transmission",
        "cross-asset repricing",
        "macro",
        0.0,
    ),
    (
        re.compile(r"(?:in\s+line|inline).{0,20}(?:estimate|expectation|consensus)", re.I),
        "results in line",
        "limited surprise",
        "fundamental",
        0.0,
    ),
]


def _best_evidence_span(text: str, cause: str, *, max_len: int = 180) -> str:
    lower = text.lower()
    cause_tokens = [t for t in re.findall(r"[a-z0-9]+", cause.lower()) if len(t) > 3]
    if cause_tokens:
        for token in cause_tokens:
            idx = lower.find(token)
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(text), idx + max_len - 40)
                return text[start:end].strip()
    return text[:max_len].strip()


def _infer_from_extractor(extracted_by: str, text: str, domain: str) -> tuple[str, str, str]:
    mechanism = MECHANISM_CATEGORIES.get(extracted_by) or DOMAIN_DEFAULT_MECHANISM.get(domain, "fundamental")
    templates: dict[str, tuple[str, str]] = {
        "earnings_release": ("earnings disclosure", "fundamental repricing"),
        "guidance_cut": ("guidance reduction", "forward earnings revision"),
        "guidance_raise": ("guidance raise", "estimate revision upside"),
        "analyst_downgrade": ("analyst downgrade", "sentiment deterioration"),
        "analyst_upgrade": ("analyst upgrade", "sentiment improvement"),
        "short_seller_report": ("short seller allegations", "trust collapse"),
        "news_amplification": ("negative news amplification", "attention-driven selling"),
        "social_discussion_spike": ("social attention spike", "narrative acceleration"),
        "fomc_statement": ("FOMC policy decision", "macro risk repricing"),
        "cpi_surprise": ("CPI surprise", "inflation path repricing"),
        "macro_rate_shock": ("rate shock", "discount rate repricing"),
        "sector_etf_movement": ("sector move", "beta transmission"),
        "options_vol": ("options activity spike", "dealer hedging pressure"),
        "market_move": ("price move", "momentum feedback"),
        "transcript_quote": ("management commentary", "narrative shift"),
    }
    if extracted_by in templates:
        cause, effect = templates[extracted_by]
        return cause, effect, mechanism

    tone = infer_tone(text)
    if tone < -0.2:
        return "negative fundamental signal", "downside pressure", mechanism
    if tone > 0.2:
        return "positive fundamental signal", "upside pressure", mechanism
    return "market-relevant disclosure", "price sensitivity", mechanism


def _claim_polarity_from_text(text: str) -> float:
    if _BOILERPLATE.search(text):
        for pattern, _, _, _, polarity in CAUSE_EFFECT_HINTS:
            if abs(polarity) >= 1.0 and pattern.search(text):
                return polarity
        return 0.0
    for pattern, _, _, _, polarity in CAUSE_EFFECT_HINTS:
        if pattern.search(text):
            return polarity
    tone = infer_tone(text)
    if tone <= -0.25:
        return -1.0
    if tone >= 0.25:
        return 1.0
    return 0.0


def _build_claim(
    *,
    atom: MarketAtom,
    cause: str,
    effect: str,
    mechanism: str,
    severity: float,
    polarity: float,
) -> dict[str, Any]:
    return {
        "cause": cause,
        "effect": effect,
        "mechanism": mechanism,
        "severity": round(severity, 3),
        "polarity": round(polarity, 3),
        "evidence_span": _best_evidence_span(atom.text, cause),
        "source_id": atom.atom_id,
        "published_at": atom.effective_time(),
        "proposer": "heuristic",
    }


_BOILERPLATE = re.compile(
    r"forward-looking statements|Private Securities Litigation Reform Act|Securities and Exchange Commission",
    re.I,
)


def _pattern_matches(text: str, pattern: re.Pattern[str], *, polarity: float) -> bool:
    if not pattern.search(text):
        return False
    if _BOILERPLATE.search(text) and abs(polarity) < 1.0:
        return False
    return True


def propose_claims_heuristic(atom: MarketAtom, domain: str) -> list[dict[str, Any]]:
    text = atom.text.strip()
    if len(text) < 12:
        return []

    extracted_by = str(atom.metadata.get("extracted_by", ""))
    base_severity = float(atom.metadata.get("severity") or infer_severity(text))
    earnings_like = extracted_by in {
        "earnings_release",
        "financial_results",
        "heuristic_earnings",
        "guidance_cut",
        "guidance_raise",
    } or domain == "earnings"

    matched: list[dict[str, Any]] = []
    seen_causes: set[str] = set()
    for pattern, p_cause, p_effect, p_mech, polarity in CAUSE_EFFECT_HINTS:
        if not _pattern_matches(text, pattern, polarity=polarity):
            continue
        if p_cause in seen_causes:
            continue
        seen_causes.add(p_cause)
        severity = min(0.98, base_severity + 0.08 * abs(polarity))
        matched.append(
            _build_claim(
                atom=atom,
                cause=p_cause,
                effect=p_effect,
                mechanism=p_mech,
                severity=severity,
                polarity=polarity,
            )
        )
        if len(matched) >= 3:
            break

    if matched:
        return matched

    cause, effect, mechanism = _infer_from_extractor(extracted_by, text, domain)
    polarity = _claim_polarity_from_text(text)
    return [
        _build_claim(
            atom=atom,
            cause=cause,
            effect=effect,
            mechanism=mechanism,
            severity=base_severity,
            polarity=polarity,
        )
    ]


def _build_llm_prompt(atom: MarketAtom, domain: str) -> str:
    return f"""Extract ONE causal market claim from this evidence atom.

Domain: {domain}
Atom ID: {atom.atom_id}
Published minute: {atom.effective_time()}
Tags: {", ".join(atom.tags)}
Text: {atom.text}

Return ONLY JSON with fields:
cause, effect, mechanism, severity, polarity, evidence_span, source_id, published_at

Rules:
- mechanism must be one of: fundamental, sentiment, liquidity, macro, regulatory, trust
- severity is 0.0-1.0
- polarity is -1.0 (bearish), 0.0 (neutral), or 1.0 (bullish); sign must match evidence tone
- effect must describe a market mechanism (estimate revision, margin shift, guidance change) — NOT "stock goes up/down"
- evidence_span MUST be an exact substring of the atom text (>= 20 chars)
- source_id must be "{atom.atom_id}"
- published_at must be {atom.effective_time()}
"""


def propose_claims_llm(
    atom: MarketAtom,
    domain: str,
    *,
    use_api: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    if not use_api:
        return propose_claims_heuristic(atom, domain)

    api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY")
    if not api_key:
        return propose_claims_heuristic(atom, domain)

    base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://ai.azya.top/v1").rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL") or "qwen3.5"
    prompt = _build_llm_prompt(atom, domain)

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "Respond with valid JSON only. No markdown."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()
        raw = json.loads(content)
        if isinstance(raw, list):
            claims = raw
        else:
            claims = [raw]
        for claim in claims:
            claim["proposer"] = "llm"
            if "polarity" not in claim:
                claim["polarity"] = _claim_polarity_from_text(
                    f"{claim.get('cause', '')} {claim.get('effect', '')} {claim.get('evidence_span', '')}"
                )
        return claims
    except Exception:  # noqa: BLE001
        return propose_claims_heuristic(atom, domain)


def propose_claims(
    atom: MarketAtom,
    domain: str,
    *,
    use_llm: bool = False,
) -> list[dict[str, Any]]:
    return propose_claims_llm(atom, domain, use_api=use_llm)
