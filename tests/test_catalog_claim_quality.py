"""Tests for catalog LLM claim quality policy."""

from __future__ import annotations

from market_causal_engine.benchmark.catalog.claim_quality import (
    CatalogClaimsPolicy,
    apply_catalog_claims_policy,
    is_heuristic_claims_doc,
    is_llm_claims_doc,
)


def _llm_doc(**overrides):
    base = {
        "use_llm": True,
        "llm_proposer": "llm_event",
        "accepted": [
            {
                "cause": "revenue beat",
                "effect": "bullish reaction",
                "evidence_span": "revenue exceeded expectations",
                "confidence": 0.8,
                "severity": 0.7,
                "polarity": 0.8,
            },
            {
                "cause": "guidance raised",
                "effect": "positive outlook",
                "evidence_span": "raised full-year guidance",
                "confidence": 0.75,
                "severity": 0.6,
                "polarity": 0.6,
            },
        ],
    }
    base.update(overrides)
    return base


def test_heuristic_doc_rejected_by_default_policy():
    doc = {"use_llm": False, "accepted": [{"cause": "x", "effect": "y", "polarity": 0.5, "confidence": 0.7, "severity": 0.5}]}
    assert is_heuristic_claims_doc(doc)
    assert not is_llm_claims_doc(doc)
    assert apply_catalog_claims_policy(doc) is None


def test_llm_doc_passes_with_two_directional_claims():
    out = apply_catalog_claims_policy(_llm_doc())
    assert out is not None
    assert out["claim_count"] == 2
    assert out["catalog_net_polarity"] > 0


def test_single_weak_claim_rejected():
    doc = _llm_doc(
        accepted=[
            {
                "cause": "generic filing",
                "effect": "unclear",
                "evidence_span": "forward-looking statements",
                "confidence": 0.4,
                "severity": 0.2,
                "polarity": 0.0,
            }
        ]
    )
    assert apply_catalog_claims_policy(doc) is None


def test_prune_stored_claims_keeps_top_signals():
    from market_causal_engine.benchmark.catalog.claim_quality import prune_stored_claims

    claims = [
        {
            "confidence": 0.9,
            "polarity": 0.8,
            "severity": 0.8,
            "cause": "beat",
            "effect": "estimate revision upside",
            "evidence_span": "revenue exceeded expectations and beat estimates",
        },
        {
            "confidence": 0.4,
            "polarity": 0.1,
            "severity": 0.5,
            "cause": "weak",
            "effect": "positive next-day stock direction",
            "evidence_span": "revenue was in line with expectations",
        },
        {
            "confidence": 0.85,
            "polarity": -0.7,
            "severity": 0.7,
            "cause": "miss",
            "effect": "guidance cut lowers FY outlook",
            "evidence_span": "lowered full-year guidance due to demand weakness",
        },
    ]
    pruned = prune_stored_claims(claims, max_claims=2)
    assert len(pruned) == 2
    assert pruned[0]["cause"] == "beat"
    assert all("polarity_source" in claim for claim in pruned)


def test_generic_effect_rewritten_on_enrich():
    from market_causal_engine.benchmark.catalog.claim_quality import enrich_extracted_claim, is_generic_effect

    claim = enrich_extracted_claim(
        {
            "cause": "record net income",
            "effect": "positive next-day stock direction",
            "evidence_span": "all-time net income record of 22.2 billion",
            "polarity": 0.5,
            "confidence": 0.7,
            "mechanism": "fundamental",
        }
    )
    assert not is_generic_effect(claim["effect"])
    assert claim.get("effect_rewritten") is True
    assert claim["polarity"] > 0


def test_refine_claim_polarity_prefers_evidence():
    from market_causal_engine.benchmark.catalog.claim_quality import refine_claim_polarity

    claim = refine_claim_polarity(
        {
            "cause": "earnings miss",
            "effect": "valuation de-rating",
            "polarity": 0.8,
            "evidence_span": "revenue missed estimates and declined 12 percent year over year",
        }
    )
    assert claim["polarity"] < 0
    assert claim["polarity_source"] == "evidence"


def test_filter_rewrites_generic_effects():
    from market_causal_engine.benchmark.catalog.claim_quality import is_generic_effect

    doc = _llm_doc(
        accepted=[
            {
                "cause": "record revenue",
                "effect": "positive next-day stock direction",
                "evidence_span": "record quarterly revenue growth",
                "confidence": 0.8,
                "severity": 0.7,
                "polarity": 0.8,
            },
            {
                "cause": "guidance raised",
                "effect": "estimate revision upside",
                "evidence_span": "raised full-year guidance",
                "confidence": 0.75,
                "severity": 0.6,
                "polarity": 0.6,
            },
            {
                "cause": "margin expansion",
                "effect": "operating margin improvement",
                "evidence_span": "operating margin expanded 120 basis points",
                "confidence": 0.72,
                "severity": 0.65,
                "polarity": 0.55,
            },
        ]
    )
    out = apply_catalog_claims_policy(doc)
    assert out is not None
    assert len(out["accepted"]) >= 2
    assert all(not is_generic_effect(c["effect"]) for c in out["accepted"])


def test_atom_fallback_rejected_by_default():
    doc = _llm_doc(llm_proposer="llm_atom_fallback")
    assert apply_catalog_claims_policy(doc) is None


def test_min_net_polarity_filter():
    doc = _llm_doc(
        accepted=[
            {
                "cause": "mixed",
                "effect": "mixed outlook on revenue",
                "evidence_span": "results were in line with analyst expectations",
                "confidence": 0.8,
                "severity": 0.7,
                "polarity": 0.05,
            },
            {
                "cause": "mixed2",
                "effect": "mixed outlook on margins",
                "evidence_span": "operating margins were consistent with prior quarter",
                "confidence": 0.8,
                "severity": 0.7,
                "polarity": -0.04,
            },
        ]
    )
    strict = CatalogClaimsPolicy(min_net_polarity=0.08)
    assert apply_catalog_claims_policy(doc, strict) is None
    loose = CatalogClaimsPolicy(
        min_accepted_claims=2,
        min_net_polarity=0.0,
        min_claim_polarity=0.0,
        min_claim_confidence=0.0,
    )
    assert apply_catalog_claims_policy(doc, loose) is not None
