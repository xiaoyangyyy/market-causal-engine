"""Tests for Phase 2 causal claim extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_causal_engine.evidence import MarketAtom, load_atoms
from market_causal_engine.extraction.atom_scorer import score_claim, score_evidence_span
from market_causal_engine.extraction.causal_claim_extractor import (
    extract_claims_for_atoms,
    extract_claims_for_case,
)
from market_causal_engine.extraction.llm_extractor import propose_claims_heuristic
from market_causal_engine.extraction.rule_validator import validate_claim, validate_claim_schema
from market_causal_engine.lookahead import LookAheadPolicy

ROOT = Path(__file__).resolve().parent.parent


def _sample_atom() -> MarketAtom:
    return MarketAtom(
        atom_id="TEST_001",
        text="The company reported a net loss of 200,000 paid memberships in Q1 versus consensus expectations.",
        source="8-K",
        time=0,
        tags=["earnings"],
        metadata={"severity": 0.85, "extracted_by": "earnings_release", "source_class": "primary_filing"},
        published_at=0,
    )


def test_schema_rejects_missing_fields():
    result = validate_claim_schema({"cause": "x"})
    assert result.passed is False
    assert any("missing_field" in e for e in result.errors)


def test_heuristic_proposal_shape():
    atom = _sample_atom()
    proposals = propose_claims_heuristic(atom, "earnings")
    assert proposals
    claim = proposals[0]
    assert claim["mechanism"] in ("fundamental", "sentiment", "liquidity", "macro", "trust", "regulatory")
    assert claim["evidence_span"].lower() in atom.text.lower()


def test_validate_claim_passes_good_proposal():
    atom = _sample_atom()
    proposal = propose_claims_heuristic(atom, "earnings")[0]
    result = validate_claim(proposal, atom, domain="earnings", as_of=120)
    assert result.passed is True


def test_validate_claim_rejects_lookahead():
    atom = _sample_atom()
    proposal = propose_claims_heuristic(atom, "earnings")[0]
    proposal["published_at"] = 999
    result = validate_claim(
        proposal,
        atom,
        domain="earnings",
        as_of=10,
        policy=LookAheadPolicy(strict=True),
    )
    assert result.passed is False
    assert "lookahead_violation" in result.errors


def test_span_scoring():
    atom = _sample_atom()
    score = score_evidence_span("net loss of 200,000 paid memberships", atom.text)
    assert score >= 0.85


def test_extract_claims_for_nflx_case():
    out = extract_claims_for_case("nflx_2022q1_earnings", write=False)
    assert out["claim_count"] >= 3
    # Trap / post-hoc atoms should be rejected by lookahead and source rules.
    assert out["rejected_count"] >= 1
    rejected_ids = {r["atom_id"] for r in out["rejected"]}
    assert "NFLX22Q1_TRAP_NEXTDAY" in rejected_ids
    top = out["accepted"][0]
    assert "claim_id" in top
    assert top["confidence"] > 0.5


def test_extract_claims_batch_atoms():
    atoms = load_atoms(ROOT / "data" / "market" / "case_studies" / "fomc_2022_75bp" / "atoms.jsonl")
    out = extract_claims_for_atoms(
        atoms,
        domain="macro",
        as_of=180,
        case_prefix="FOMC22",
    )
    assert out["claim_count"] >= 3


@pytest.mark.parametrize("case_id", ["meta_2022q4_earnings", "hindenburg_nikola_2020", "gme_2021_01_squeeze"])
def test_extract_claims_case_variants(case_id: str):
    out = extract_claims_for_case(case_id, write=False)
    assert out["claim_count"] >= 2
