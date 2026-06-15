"""Score proposed causal claims against source atoms."""

from __future__ import annotations

import re
from typing import Any

from market_causal_engine.evidence import MarketAtom


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def score_evidence_span(span: str, atom_text: str) -> float:
    """0-1 score: substring match + token overlap."""
    span = span.strip()
    if not span or not atom_text:
        return 0.0
    lower_atom = atom_text.lower()
    lower_span = span.lower()
    if lower_span in lower_atom:
        base = 0.85
    else:
        span_tokens = _token_set(lower_span)
        atom_tokens = _token_set(lower_atom)
        if not span_tokens:
            return 0.0
        overlap = len(span_tokens & atom_tokens) / len(span_tokens)
        base = 0.35 * overlap

    # Reward longer, specific spans up to a cap.
    length_bonus = min(0.15, len(span) / max(len(atom_text), 1) * 0.2)
    return round(min(1.0, base + length_bonus), 3)


def score_claim(claim: dict[str, Any], atom: MarketAtom) -> dict[str, Any]:
    span_score = score_evidence_span(str(claim.get("evidence_span", "")), atom.text)
    severity = float(claim.get("severity", 0.0))
    meta_severity = float(atom.metadata.get("severity", severity))
    severity_align = 1.0 - min(1.0, abs(severity - meta_severity))

    extracted_by = str(atom.metadata.get("extracted_by", ""))
    mechanism = str(claim.get("mechanism", ""))
    mechanism_hint = 1.0 if _mechanism_matches_extractor(mechanism, extracted_by) else 0.6

    from market_causal_engine.benchmark.catalog.claim_quality import effect_specificity_score, is_generic_effect

    effect = str(claim.get("effect", ""))
    specificity = effect_specificity_score(effect)
    generic_penalty = 0.0 if is_generic_effect(effect) else 0.12 * specificity

    confidence = round(
        0.50 * span_score + 0.22 * severity_align + 0.18 * mechanism_hint + generic_penalty,
        3,
    )
    return {
        "confidence": confidence,
        "span_score": span_score,
        "severity_align": round(severity_align, 3),
        "mechanism_hint": mechanism_hint,
    }


def rank_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(claims, key=lambda c: float(c.get("confidence", 0.0)), reverse=True)


def _mechanism_matches_extractor(mechanism: str, extracted_by: str) -> bool:
    mapping = {
        "earnings_release": "fundamental",
        "earnings_miss": "fundamental",
        "guidance_cut": "fundamental",
        "guidance_raise": "fundamental",
        "analyst_downgrade": "sentiment",
        "analyst_upgrade": "sentiment",
        "short_seller_report": "trust",
        "trust_erosion": "trust",
        "regulatory_probe": "regulatory",
        "liquidity_dry_up": "liquidity",
        "option_gamma_pressure": "liquidity",
        "fomc_statement": "macro",
        "cpi_surprise": "macro",
        "macro_rate_shock": "macro",
        "sector_etf_movement": "macro",
        "social_discussion_spike": "sentiment",
        "news_amplification": "sentiment",
    }
    expected = mapping.get(extracted_by)
    return expected is None or mechanism == expected
