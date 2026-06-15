"""Tests for historical case studies and look-ahead validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_causal_engine.case_study import (
    list_case_studies,
    load_case_manifest,
    run_case_counterfactual,
    run_case_study,
)
from market_causal_engine.evidence import MarketAtom, load_atoms
from market_causal_engine.lookahead import LookAheadPolicy, filter_admissible_atoms, validate_atom


ROOT = Path(__file__).resolve().parent.parent
NFLX = ROOT / "data" / "market" / "case_studies" / "nflx_2022q1_earnings"
SNAP = ROOT / "data" / "market" / "case_studies" / "snap_2022q3_earnings"


def test_list_case_studies():
    cases = list_case_studies()
    ids = {c["case_id"] for c in cases}
    assert "nflx_2022q1_earnings" in ids
    assert "snap_2022q3_earnings" in ids
    assert "meta_2022q4_earnings" in ids
    assert "hindenburg_nikola_2020" in ids
    assert "fomc_2022_75bp" in ids
    assert "shop_2022q2_earnings" in ids
    assert "cpi_2022_06_hot" in ids
    assert "gme_2021_01_squeeze" in ids
    assert "luckin_2020_fraud" in ids


def test_lookahead_rejects_future_published_at():
    atom = MarketAtom(
        atom_id="T1",
        text="Next day analyst cuts",
        source="analyst",
        time=100,
        published_at=500,
        tags=["analyst"],
    )
    vr = validate_atom(atom, as_of=120)
    assert not vr.accepted
    assert vr.reason_code == "lookahead_published_at"


def test_lookahead_rejects_post_hoc_source_class():
    atom = MarketAtom(
        atom_id="T2",
        text="Two-day return was -37%",
        source="research",
        time=60,
        published_at=60,
        tags=[],
        metadata={"source_class": "calibration_label", "uses_future_price": True},
    )
    vr = validate_atom(atom, as_of=120, policy=LookAheadPolicy())
    assert not vr.accepted
    assert vr.reason_code in ("forbidden_post_hoc_source", "future_price_leak")


def test_lookahead_rejects_next_day_only():
    atom = MarketAtom(
        atom_id="T3",
        text="Analyst downgrade next morning",
        source="analyst",
        time=960,
        published_at=960,
        tags=["analyst"],
        metadata={"source_class": "next_day_only"},
    )
    vr = validate_atom(atom, as_of=120)
    assert not vr.accepted


def test_nflx_feed_traps_rejected_at_120():
    atoms = load_atoms(NFLX / "atoms.jsonl")
    _, report = filter_admissible_atoms(atoms, as_of=120, policy=LookAheadPolicy())
    rejected_ids = {v.atom_id for v in report.rejected_atoms}
    assert "NFLX22Q1_TRAP_NEXTDAY" in rejected_ids
    assert "NFLX22Q1_TRAP_ANALYST" in rejected_ids
    assert report.accepted_count >= 6


def test_nflx_validate_lookahead_only():
    result = run_case_study("nflx_2022q1_earnings", validate_only=True, as_of=120)
    assert result["lookahead_audit"]["rejected_count"] >= 2
    assert result["atom_count_admissible"] >= 6


def test_nflx_case_study_replay():
    result = run_case_study("nflx_2022q1_earnings", as_of=120, until=120)
    assert result["case_study"]["feed_only"] is True
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "earnings"
    risk = result["final_risk"]
    assert 0.2 < risk["drawdown_risk"] < 0.9
    assert risk["directional_pressure"] > 0.15
    assert result["calibrated_impact"].get("after_hours_error_pct", 99) <= 18.0
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "earnings_release" in kinds or "guidance_cut" in kinds
    assert result["case_study"]["atoms_rejected_lookahead"] >= 2


def test_nflx_dominant_path_includes_guidance_or_downgrade():
    result = run_case_study("nflx_2022q1_earnings", as_of=120)
    path = result["dominant_causal_path"]
    assert any(k in path for k in ("guidance_cut", "analyst_downgrade", "earnings_miss"))


def test_nflx_counterfactual_w1_lowers_drawdown():
    w0 = run_case_study("nflx_2022q1_earnings", world_id="W0", as_of=120)
    w1 = run_case_study("nflx_2022q1_earnings", world_id="W1", as_of=120)
    assert w1["final_risk"]["drawdown_risk"] <= w0["final_risk"]["drawdown_risk"]


def test_nflx_mechanism_contributions():
    result = run_case_study("nflx_2022q1_earnings", as_of=120)
    contrib = result["mechanism_contributions"]
    assert contrib["fundamental"] + contrib["sentiment"] + contrib["liquidity"] > 0


def test_snap_case_study_replay():
    result = run_case_study("snap_2022q3_earnings", as_of=100)
    assert result["case_study"]["direction_match"] is True
    assert result["ticker"] == "SNAP" if "ticker" in result else result["case_study"]["ticker"] == "SNAP"


def test_case_counterfactual_suite():
    suite = run_case_counterfactual("nflx_2022q1_earnings", until=120)
    assert "W0" in suite["runs"]
    assert "W1" in suite["counterfactual_diffs"]


def test_manifest_load():
    m = load_case_manifest("nflx_2022q1_earnings")
    assert m["ticker"] == "NFLX"
    assert m["observed_outcomes"]["direction"] == "down"


def test_meta_case_study_replay():
    result = run_case_study("meta_2022q4_earnings", as_of=120)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "earnings"
    assert result["final_risk"]["drawdown_risk"] > 0.38
    assert result["calibrated_impact"].get("after_hours_error_pct", 99) <= 18.0


def test_hindenburg_case_study_replay():
    result = run_case_study("hindenburg_nikola_2020", as_of=120)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "short_report"
    assert result["final_risk"]["drawdown_risk"] > 0.35
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "short_seller_report" in kinds


def test_fomc_case_study_replay():
    result = run_case_study("fomc_2022_75bp", as_of=90)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "macro"
    cal = result.get("calibrated_impact", {})
    assert cal.get("after_hours_error_pct", 99) <= 8.0


def test_gme_squeeze_replay():
    result = run_case_study("gme_2021_01_squeeze", as_of=390)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "short_report"
    cal = result.get("calibrated_impact", {})
    assert cal.get("after_hours_error_pct", 99) <= 12.0


def test_luckin_fraud_replay():
    result = run_case_study("luckin_2020_fraud", as_of=120)
    assert result["case_study"]["direction_match"] is True
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "short_seller_report" in kinds
    cal = result.get("calibrated_impact", {})
    assert cal.get("after_hours_error_pct", 99) <= 10.0


def test_shop_case_study_replay():
    result = run_case_study("shop_2022q2_earnings", as_of=120)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "earnings"
    assert result["calibrated_impact"].get("after_hours_within_band") is True


def test_cpi_case_study_replay():
    result = run_case_study("cpi_2022_06_hot", as_of=90)
    assert result["case_study"]["direction_match"] is True
    assert result["domain"] == "macro"
    cal = result.get("calibrated_impact", {})
    assert cal.get("after_hours_error_pct", 99) <= 8.0
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "cpi_surprise" in kinds
