"""Tests for SEC/news atom extraction pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_causal_engine.extraction.pipeline import (
    build_atoms_for_case,
    extract_from_case,
    list_extractable_cases,
)
from market_causal_engine.evidence import load_atoms

ROOT = Path(__file__).resolve().parent.parent


def test_list_extractable_cases():
    cases = list_extractable_cases()
    assert "meta_2022q4_earnings" in cases
    assert "hindenburg_nikola_2020" in cases
    assert "fomc_2022_75bp" in cases
    assert "nflx_2022q1_earnings" in cases
    assert "shop_2022q2_earnings" in cases
    assert "cpi_2022_06_hot" in cases


@pytest.mark.parametrize(
    "case_id,min_atoms",
    [
        ("meta_2022q4_earnings", 8),
        ("hindenburg_nikola_2020", 5),
        ("fomc_2022_75bp", 5),
    ],
)
def test_extract_from_case(case_id: str, min_atoms: int):
    atoms, report = extract_from_case(case_id)
    assert report["atom_count"] == len(atoms)
    assert len(atoms) >= min_atoms
    assert all(a.atom_id for a in atoms)
    assert all(a.published_at is not None for a in atoms)


def test_build_atoms_writes_jsonl(tmp_path, monkeypatch):
    case_id = "fomc_2022_75bp"
    case_root = ROOT / "data" / "market" / "case_studies" / case_id
    out = tmp_path / "atoms.jsonl"
    monkeypatch.setattr(
        "market_causal_engine.extraction.pipeline._case_root",
        lambda cid: case_root if cid == case_id else tmp_path / cid,
    )

    result = build_atoms_for_case(case_id, write=False, validate_lookahead=True)
    assert result["atom_count"] >= 5
    assert result["lookahead_passed"] is True


def test_meta_atoms_compile_earnings_tags():
    atoms = load_atoms(ROOT / "data" / "market" / "case_studies" / "meta_2022q4_earnings" / "atoms.jsonl")
    earnings = [a for a in atoms if "earnings" in a.tags]
    assert len(earnings) >= 3
    analyst = [a for a in atoms if "analyst" in a.tags]
    assert len(analyst) >= 1
