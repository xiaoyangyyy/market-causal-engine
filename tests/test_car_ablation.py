"""Tests for CAR ablation channel contributions."""

from __future__ import annotations

from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.validation import run_ablation_suite, summarize_ablation
from market_causal_engine.case_study import load_case_manifest, run_case_study
from market_causal_engine.counterfactuals.car_ablation import (
    channel_contribution_row,
    predicted_return_pct,
    run_car_ablation,
)
from market_causal_engine.counterfactuals.outcome_layer import attach_outcome_causal


def test_predicted_return_pct_from_calibration():
    result = {"calibrated_impact": {"estimated_after_hours_return_pct": -22.5}}
    assert predicted_return_pct(result) == -22.5


def test_channel_contribution_row_signed_share():
    baseline = {
        "calibrated_impact": {"estimated_after_hours_return_pct": -25.0},
        "dominant_causal_path": ["a", "b"],
        "final_risk": {"directional_pressure": 0.5, "drawdown_risk": 0.7},
    }
    ablated = {
        "calibrated_impact": {"estimated_after_hours_return_pct": -10.0},
        "dominant_causal_path": ["a"],
        "final_risk": {"directional_pressure": 0.2, "drawdown_risk": 0.3},
    }
    row = channel_contribution_row(
        channel="no_sec",
        baseline_result=baseline,
        ablated_result=ablated,
        baseline_pred=-25.0,
        observed_car=-32.15,
    )
    assert row["marginal_return_pct"] == -15.0
    assert abs(row["share_of_observed_car"] - 0.4665) < 0.01
    assert row["path_changed"] is True


def test_nflx_car_ablation_integration():
    case_id = "nflx_2022q1_earnings"
    manifest = load_case_manifest(case_id)
    event = BenchmarkEvent(
        event_id=case_id,
        corpus="case_study",
        ticker=manifest["ticker"],
        event_date=manifest["event_date"],
        event_type=manifest["event_type"],
        domain=manifest["domain"],
        replay_mode="case_study",
        case_id=case_id,
    )
    result = run_case_study(case_id, as_of=60)
    attach_outcome_causal(result, event, run_placebo=False, car_ablation=True, until=60)

    oc = result["outcome_causal"]
    assert oc.get("event_study", {}).get("CAR") is not None
    car_ab = oc.get("car_ablation")
    assert car_ab is not None
    assert car_ab["observed_car_pct"] is not None
    assert car_ab["baseline_predicted_return_pct"] is not None
    assert len(car_ab["channels"]) == 3
    assert car_ab["dominant_channel"] in {"no_news", "no_sec", "no_price"}
    for ch, stats in car_ab["channels"].items():
        assert stats["marginal_return_pct"] is not None
        assert stats["share_of_observed_car"] is not None


def test_ablation_suite_includes_car_metrics():
    results = run_ablation_suite(["nflx_2022q1_earnings"], until=60)
    assert len(results) == 3
    assert results[0].observed_car_pct is not None
    assert results[0].marginal_return_pct is not None
    summary = summarize_ablation(results)
    assert "car_by_channel" in summary
    assert "car_by_case" in summary
    assert "nflx_2022q1_earnings" in summary["car_by_case"]


def test_run_car_ablation_standalone():
    case_id = "nflx_2022q1_earnings"
    manifest = load_case_manifest(case_id)
    event = BenchmarkEvent(
        event_id=case_id,
        corpus="case_study",
        ticker=manifest["ticker"],
        event_date=manifest["event_date"],
        event_type=manifest["event_type"],
        domain=manifest["domain"],
        replay_mode="case_study",
        case_id=case_id,
    )
    baseline = run_case_study(case_id, as_of=60)
    attach_outcome_causal(baseline, event, run_placebo=False, car_ablation=False, until=60)
    car = run_car_ablation(event, baseline, until=60)
    assert car is not None
    assert car["n_channels"] == 3
