"""Quality policy for catalog LLM causal claims (no heuristic path)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BOILERPLATE_RE = re.compile(
    r"forward.?looking|safe harbor|sec rules|private securities|undue reliance",
    re.IGNORECASE,
)

GENERIC_EFFECT_RE = re.compile(
    r"next.?day\s+(?:stock\s+)?(?:direction|reaction|move|impact)"
    r"|(?:positive|negative|bullish|bearish)\s+(?:next.?day|stock|market|investor)\s+(?:reaction|direction|move|sentiment|impact)"
    r"|(?:stock|share)\s+price\s+(?:direction|move|reaction|impact)"
    r"|(?:upside|downside)\s+pressure"
    r"|price\s+sensitivity"
    r"|market.?relevant\s+disclosure"
    r"|unclear(?:\s+impact)?"
    r"|(?:likely|potential)\s+(?:stock|market|price)\s+(?:move|reaction)",
    re.IGNORECASE,
)

SPECIFIC_EFFECT_HINTS = re.compile(
    r"\b(?:margin|revenue|eps|earnings|guidance|subscriber|estimate|valuation|de-?rating|"
    r"revision|cash flow|operating income|operating margin|same-store|comparable|segment|"
    r"outlook|forecast|beat|miss|growth|decline|loss|profit|demand|pricing|backlog|"
    r"orders|inventory|dividend|buyback|leverage|debt|capex|roi|roic|ebitda)\b",
    re.IGNORECASE,
)

POLICY_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "market"
    / "learned"
    / "catalog_claims_policy.json"
)


@dataclass(frozen=True)
class CatalogClaimsPolicy:
    """Filter heuristic claims and low-signal LLM extractions."""

    llm_only: bool = True
    min_accepted_claims: int = 2
    min_claim_confidence: float = 0.50
    min_claim_polarity: float = 0.10
    min_claim_severity: float = 0.0
    min_net_polarity: float = 0.08
    exclude_boilerplate: bool = True
    exclude_generic_effects: bool = True
    exclude_atom_fallback: bool = True
    require_event_proposer: bool = True
    max_claims_per_event: int = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogClaimsPolicy:
        known = {field for field in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


DEFAULT_LLM_QUALITY_POLICY = CatalogClaimsPolicy()


def is_llm_claims_doc(doc: dict[str, Any]) -> bool:
    return bool(doc.get("use_llm")) and str(doc.get("llm_proposer", "")).startswith("llm")


def is_heuristic_claims_doc(doc: dict[str, Any]) -> bool:
    return bool(doc.get("accepted")) and not is_llm_claims_doc(doc)


def _claim_text(claim: dict[str, Any]) -> str:
    return " ".join(str(claim.get(key, "")) for key in ("cause", "effect", "evidence_span") if claim.get(key))


def is_generic_effect(text: str) -> bool:
    """True when effect text is vague stock-direction language instead of a mechanism."""
    cleaned = str(text or "").strip()
    if not cleaned or len(cleaned) < 8:
        return True
    if GENERIC_EFFECT_RE.search(cleaned):
        return True
    if cleaned.lower() in {"up", "down", "neutral", "positive", "negative", "bullish", "bearish"}:
        return True
    return False


def effect_specificity_score(effect: str) -> float:
    """0-1 score: quantified / mechanism-specific effects rank higher."""
    cleaned = str(effect or "").strip()
    if not cleaned or is_generic_effect(cleaned):
        return 0.0
    score = 0.25
    if re.search(r"\d", cleaned):
        score += 0.35
    if SPECIFIC_EFFECT_HINTS.search(cleaned):
        score += 0.40
    return round(min(1.0, score), 3)


def _evidence_polarity(claim: dict[str, Any]) -> float:
    from market_causal_engine.extraction.llm_extractor import _claim_polarity_from_text

    evidence = str(claim.get("evidence_span", ""))
    cause = str(claim.get("cause", ""))
    if evidence:
        return float(_claim_polarity_from_text(evidence))
    return float(_claim_polarity_from_text(f"{cause} {claim.get('effect', '')}"))


def refine_claim_polarity(claim: dict[str, Any]) -> dict[str, Any]:
    """Prefer evidence-derived polarity; resolve sign conflicts in favor of filing text."""
    from market_causal_engine.extraction.llm_extractor import _claim_polarity_from_text

    out = dict(claim)
    evidence_pol = _evidence_polarity(out)
    full_pol = float(
        _claim_polarity_from_text(
            f"{out.get('cause', '')} {out.get('effect', '')} {out.get('evidence_span', '')}"
        )
    )
    llm_pol = float(out.get("polarity", 0.0))

    if abs(evidence_pol) >= 0.5:
        final = evidence_pol
    elif abs(full_pol) >= 0.5:
        final = full_pol
    elif abs(llm_pol) >= 0.25 and abs(evidence_pol) < 0.25:
        final = llm_pol
    else:
        final = full_pol if abs(full_pol) >= abs(llm_pol) else llm_pol

    if evidence_pol != 0.0 and llm_pol != 0.0 and (evidence_pol * llm_pol < 0) and abs(evidence_pol) >= 0.5:
        final = evidence_pol

    out["polarity"] = round(max(-1.0, min(1.0, final)), 3)
    out["polarity_source"] = (
        "evidence"
        if abs(evidence_pol) >= 0.5
        else ("full_text" if abs(full_pol) >= abs(llm_pol) else "llm")
    )
    return out


def _infer_mechanism_effect(claim: dict[str, Any]) -> str:
    """Derive a specific mechanism effect from cause/evidence when LLM effect is vague."""
    from market_causal_engine.extraction.llm_extractor import CAUSE_EFFECT_HINTS

    text = f"{claim.get('cause', '')} {claim.get('evidence_span', '')}"
    for pattern, _, p_effect, _, _ in CAUSE_EFFECT_HINTS:
        if pattern.search(text):
            return p_effect

    pol = float(claim.get("polarity", 0.0))
    mechanism = str(claim.get("mechanism", "fundamental")).lower()
    if pol >= 0.5:
        return {
            "fundamental": "estimate revision upside",
            "sentiment": "sentiment improvement",
            "liquidity": "liquidity support",
            "macro": "macro tailwind",
            "regulatory": "regulatory relief",
            "trust": "trust recovery",
        }.get(mechanism, "estimate revision upside")
    if pol <= -0.5:
        return {
            "fundamental": "valuation de-rating",
            "sentiment": "sentiment deterioration",
            "liquidity": "liquidity stress",
            "macro": "macro headwind",
            "regulatory": "regulatory overhang",
            "trust": "trust erosion",
        }.get(mechanism, "valuation de-rating")
    return "limited estimate surprise"


def enrich_extracted_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Post-process one claim: refine polarity and tag effect specificity."""
    out = dict(claim)
    effect = str(out.get("effect", ""))
    if is_generic_effect(effect):
        out["effect"] = _infer_mechanism_effect(out)
        out["effect_rewritten"] = True
    out = refine_claim_polarity(out)
    effect = str(out.get("effect", ""))
    out["effect_specificity"] = effect_specificity_score(effect)
    evidence_pol = _evidence_polarity(out)
    pol = float(out.get("polarity", 0.0))
    if evidence_pol != 0.0 and pol != 0.0:
        aligned = evidence_pol * pol > 0
        out["polarity_aligned"] = aligned
        if not aligned and float(out.get("confidence", 0.0)) > 0:
            out["confidence"] = round(float(out["confidence"]) * 0.75, 3)
    else:
        out["polarity_aligned"] = True
    return out


def enrich_claim_list(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_extracted_claim(claim) for claim in claims]


def needs_quality_refresh(doc: dict[str, Any] | None) -> bool:
    """True when stored claims lack enrichment or still use generic effects."""
    if not doc or not doc.get("accepted"):
        return False
    for claim in doc.get("accepted") or []:
        if is_generic_effect(str(claim.get("effect", ""))):
            return True
        if "polarity_source" not in claim:
            return True
        if float(claim.get("effect_specificity", 0.0)) < 0.25:
            return True
    return False


def refine_stored_claims_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Offline pass: evidence-based polarity + generic-effect prune."""
    accepted = enrich_claim_list(list(doc.get("accepted") or []))
    accepted = prune_stored_claims(accepted)
    return {
        **doc,
        "accepted": accepted,
        "claim_count": len(accepted),
        "claims_refined": True,
    }


def claim_signal_score(claim: dict[str, Any]) -> float:
    """Single ranking score: confidence × |polarity| × severity × effect specificity."""
    conf = float(claim.get("confidence", 0.0))
    pol = abs(float(claim.get("polarity", 0.0)))
    sev = float(claim.get("severity", 0.0)) or 0.5
    spec = float(claim.get("effect_specificity", effect_specificity_score(str(claim.get("effect", "")))))
    spec = max(spec, 0.35)
    return conf * pol * sev * spec


def prune_stored_claims(
    claims: list[dict[str, Any]],
    *,
    max_claims: int = 5,
    min_confidence: float = 0.45,
    min_polarity: float = 0.12,
    min_effect_specificity: float = 0.25,
    exclude_generic_effects: bool = True,
) -> list[dict[str, Any]]:
    """Drop weak claims at extraction time; keep top signals only."""
    enriched = enrich_claim_list(claims)
    kept: list[dict[str, Any]] = []
    for claim in enriched:
        if float(claim.get("confidence", 0.0)) < min_confidence:
            continue
        if abs(float(claim.get("polarity", 0.0))) < min_polarity:
            continue
        if BOILERPLATE_RE.search(_claim_text(claim)):
            continue
        if exclude_generic_effects and is_generic_effect(str(claim.get("effect", ""))):
            continue
        if float(claim.get("effect_specificity", 0.0)) < min_effect_specificity:
            continue
        kept.append(claim)
    kept.sort(key=claim_signal_score, reverse=True)
    return kept[:max_claims]


def filter_accepted_claims(claims: list[dict[str, Any]], policy: CatalogClaimsPolicy) -> list[dict[str, Any]]:
    enriched = enrich_claim_list(list(claims))
    kept: list[dict[str, Any]] = []
    for claim in enriched:
        if policy.exclude_boilerplate and BOILERPLATE_RE.search(_claim_text(claim)):
            continue
        if policy.exclude_generic_effects and is_generic_effect(str(claim.get("effect", ""))):
            continue
        if float(claim.get("confidence", 0.0)) < policy.min_claim_confidence:
            continue
        if abs(float(claim.get("polarity", 0.0))) < policy.min_claim_polarity:
            continue
        if float(claim.get("severity", 0.0)) < policy.min_claim_severity:
            continue
        kept.append(claim)

    if policy.max_claims_per_event and len(kept) > policy.max_claims_per_event:
        kept = sorted(kept, key=claim_signal_score, reverse=True)[: policy.max_claims_per_event]
    return kept


def net_polarity(claims: list[dict[str, Any]]) -> float:
    weighted = 0.0
    weight_total = 0.0
    for claim in claims:
        weight = float(claim.get("confidence", 0.5)) * float(claim.get("severity", 0.5))
        if weight <= 0:
            weight = float(claim.get("confidence", 0.5))
        weighted += float(claim.get("polarity", 0.0)) * weight
        weight_total += abs(weight)
    return weighted / (weight_total or 1.0)


def event_quality_score(doc: dict[str, Any], policy: CatalogClaimsPolicy | None = None) -> float:
    claims = doc.get("accepted") or []
    if not claims:
        return 0.0
    conf = sum(float(c.get("confidence", 0.0)) for c in claims) / len(claims)
    pol = abs(net_polarity(claims))
    proposer_bonus = 0.1 if doc.get("llm_proposer") == "llm_event" else 0.0
    return round(min(1.0, 0.35 * min(len(claims), 4) / 4 + 0.35 * conf + 0.2 * pol + proposer_bonus), 4)


def apply_catalog_claims_policy(
    doc: dict[str, Any] | None,
    policy: CatalogClaimsPolicy | None = None,
) -> dict[str, Any] | None:
    """Return filtered claims doc, or None if event fails policy."""
    if not doc or not doc.get("accepted"):
        return None

    pol = policy or DEFAULT_LLM_QUALITY_POLICY
    if pol.llm_only and not is_llm_claims_doc(doc):
        return None
    if pol.require_event_proposer and doc.get("llm_proposer") != "llm_event":
        return None
    if pol.exclude_atom_fallback and doc.get("llm_proposer") == "llm_atom_fallback":
        return None

    accepted = filter_accepted_claims(list(doc.get("accepted") or []), pol)
    if len(accepted) < pol.min_accepted_claims:
        return None

    net = net_polarity(accepted)
    if abs(net) < pol.min_net_polarity:
        return None

    return {
        **doc,
        "accepted": accepted,
        "claim_count": len(accepted),
        "catalog_net_polarity": round(net, 6),
        "catalog_quality_score": event_quality_score({**doc, "accepted": accepted}, pol),
    }


def load_catalog_claims_policy(path: str | Path | None = None) -> CatalogClaimsPolicy:
    p = Path(path) if path else POLICY_PATH
    if not p.exists():
        return DEFAULT_LLM_QUALITY_POLICY
    return CatalogClaimsPolicy.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_catalog_claims_policy(policy: CatalogClaimsPolicy, path: str | Path | None = None) -> Path:
    out = Path(path) if path else POLICY_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(policy.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
