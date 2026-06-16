"""Tests for Step B outcome causal layer."""

from __future__ import annotations

from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.replay import replay_event, replay_placebo_event
from market_causal_engine.counterfactuals.outcome_layer import (
    attach_outcome_causal,
    build_event_card,
    build_outcome_card,
    event_study_metrics,
    resolve_outcome_causal,
)


def test_event_study_metrics_from_estimate():
    estimate = {
        "effect": -0.30,
        "event_window_dates": ["2022-04-19", "2022-04-20"],
        "pre_fit_rmse": 0.02,
        "estimation_days": 60,
        "placebo_rank": 1.0,
        "placebo_n": 20,
    }
    es = event_study_metrics(estimate)
    assert es["CAR"] == -0.30
    assert es["AAR"] == -0.15
    assert es["CAR_pct"] == -30.0
    assert es["t_stat"] is not None
    assert es["confidence_interval_95"]["method"] == "normal_approx_pre_rmse"


def test_event_study_ci_from_placebo():
    estimate = {
        "effect": -0.30,
        "event_window_dates": ["2022-04-19"],
        "placebo_effects": [-0.01, -0.02, -0.05, -0.10, -0.25, -0.08],
    }
    es = event_study_metrics(estimate)
    ci = es["confidence_interval_95"]
    assert ci["method"] == "placebo_percentile"
    assert "low" in ci and "high" in ci
    assert ci["low"] <= ci["high"]


def test_build_outcome_card_includes_alternates():
    estimate = {
        "method": "synthetic_control",
        "effect": -0.32,
        "event_window_dates": ["2022-04-19"],
        "alternates": {
            "factor_model": {"effect": -0.28, "method": "factor_model"},
            "abnormal_return": {"effect": -0.25, "method": "abnormal_return"},
        },
    }
    card = build_outcome_card(estimate)
    assert card["factor_adjusted_effect"] == -0.28
    assert card["synthetic_control_effect"] == -0.32
    assert "event_study" in card


def test_resolve_outcome_causal_from_corpus_cache():
    event = BenchmarkEvent(
        event_id="cached_oc",
        corpus="earnings_sp500_2016_2025",
        ticker="NFLX",
        event_date="2022-04-19",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        outcome_causal={
            "method": "abnormal_return",
            "effect": -0.25,
            "event_window": [0, 1],
            "event_window_dates": ["2022-04-19", "2022-04-20"],
        },
    )
    out = resolve_outcome_causal(event, run_placebo=False)
    assert out is not None
    assert out["method"] == "abnormal_return"
    assert out["event_study"]["CAR"] == -0.25


def test_attach_outcome_causal_placebo_event():
    event = BenchmarkEvent(
        event_id="placebo_test",
        corpus="placebo_quiet_days",
        ticker="SPY",
        event_date="2019-01-07",
        event_type="none",
        domain="placebo",
        replay_mode="placebo",
        labels={"is_placebo": True},
        scenario_id="E1",
    )
    result = replay_placebo_event(event, until=30)
    attach_outcome_causal(result, event, run_placebo=False)
    assert result["outcome_causal"]["method"] == "none"


def test_replay_event_attaches_outcome_causal():
    events = __import__(
        "market_causal_engine.benchmark.models", fromlist=["load_corpus"]
    ).load_corpus("earnings_sp500_2016_2025", max_events=50, seed=7)
    event = next((e for e in events if e.outcome_causal), events[0])
    result = replay_event(event, until=30, attach_outcome=True)
    assert "outcome_causal" in result
    oc = result["outcome_causal"]
    assert oc.get("method") not in (None, "unavailable")
    assert "event_study" in oc
    assert "CAR" in oc["event_study"]


def test_build_event_card():
    result = {
        "benchmark_event_id": "nflx_2022q1_earnings",
        "replay_mode": "case_study",
        "dominant_path": ["guidance", "valuation"],
        "simulated_direction": "down",
        "outcome_causal": {"method": "synthetic_control", "effect": -0.32},
    }
    card = build_event_card(result, event={"event_id": "nflx_2022q1_earnings", "ticker": "NFLX"})
    assert card["event_id"] == "nflx_2022q1_earnings"
    assert card["outcome_causal"]["effect"] == -0.32
