"""Tests for calibration, dampening, and full case study pipeline."""

from __future__ import annotations

import pytest

from market_causal_engine.calibration import attach_calibration, estimate_return_pct
from market_causal_engine.case_study import run_case_counterfactual, run_case_study


def test_outcome_dampening_prevents_saturation():
    w0 = run_case_study("nflx_2022q1_earnings", as_of=120)
    risk = w0["final_risk"]
    assert risk["drawdown_risk"] < 0.95
    assert risk["directional_pressure"] < 0.95


def test_calibrated_return_near_observed_nflx():
    r = run_case_study("nflx_2022q1_earnings", as_of=120)
    cal = r["calibrated_impact"]
    assert cal.get("estimated_after_hours_return_pct") is not None
    assert cal.get("magnitude_source") == "case_anchor"
    err = cal.get("after_hours_error_pct", 999)
    assert err <= 10.0, f"calibration error {err}% too large"
    assert cal.get("after_hours_within_band") is True


def test_calibrated_return_near_observed_snap():
    r = run_case_study("snap_2022q3_earnings", as_of=100)
    cal = r["calibrated_impact"]
    err = cal.get("after_hours_error_pct", 999)
    assert err <= 5.0, f"calibration error {err}% too large"


def test_nflx_w3_case_intervention_reduces_impact():
    w0 = run_case_study("nflx_2022q1_earnings", world_id="W0", as_of=120)
    w3 = run_case_study("nflx_2022q1_earnings", world_id="W3", as_of=120)
    assert w3["final_risk"]["drawdown_risk"] < w0["final_risk"]["drawdown_risk"]
    assert w0["final_risk"]["drawdown_risk"] - w3["final_risk"]["drawdown_risk"] >= 0.03


def test_snap_ad_macro_path():
    r = run_case_study("snap_2022q3_earnings", as_of=100)
    kinds = [e["kind"] for e in r["trace"] if e["action"] == "executed"]
    assert "ad_revenue_miss" in kinds
    assert any(k in kinds for k in ("digital_ad_slowdown", "macro_ad_budget_cut"))
    assert r["calibrated_impact"].get("after_hours_error_pct", 99) <= 5.0


def test_path_weighted_contributions_not_all_liquidity():
    r = run_case_study("nflx_2022q1_earnings", as_of=120)
    c = r["mechanism_contributions"]
    assert c["fundamental"] >= 0.15


def test_forensic_output_field():
    r = run_case_study("nflx_2022q1_earnings", as_of=120)
    assert "forensic_output" in r
    assert r.get("domain") == "earnings"


def test_counterfactual_w3_in_suite():
    suite = run_case_counterfactual("nflx_2022q1_earnings", until=120)
    w3_sim = suite["runs"]["W3"]["simulated_outcomes"]
    w0_sim = suite["runs"]["W0"]["simulated_outcomes"]
    assert w3_sim["drawdown_risk"] < w0_sim["drawdown_risk"]


def test_estimate_return_pct_helper():
    est = estimate_return_pct(0.72, observed_return_pct=-25, reference_drawdown=0.72)
    assert est == pytest.approx(-25.0, abs=0.5)
