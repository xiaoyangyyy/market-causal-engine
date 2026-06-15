"""Tests for P2 event benchmark suite."""

from __future__ import annotations

import json
from pathlib import Path

from market_causal_engine.benchmark.metrics import aggregate_scores, oot_accuracy, score_event, split_by_date
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus, list_corpora
from market_causal_engine.benchmark.replay import infer_simulated_direction, replay_placebo_event, replay_scenario_event
from market_causal_engine.benchmark.runner import BenchmarkConfig, BenchmarkRunner
from market_causal_engine.benchmark.validation import run_ablation_suite, summarize_ablation


def test_list_corpora():
    corpora = list_corpora()
    assert "earnings_sp500_2016_2025" in corpora
    assert "placebo_quiet_days" in corpora


def test_load_earnings_corpus_sample():
    events = load_corpus("earnings_sp500_2016_2025", max_events=10, seed=1)
    assert len(events) == 10
    assert events[0].replay_mode == "scenario"


def test_infer_simulated_direction():
    assert infer_simulated_direction({"final_risk": {"directional_pressure": 0.5, "drawdown_risk": 0.6}}) == "down"
    assert infer_simulated_direction({"final_risk": {"directional_pressure": -0.1, "drawdown_risk": 0.1}}) == "up"


def test_score_event_neutral_observed_matches_neutral_sim():
    event = BenchmarkEvent(
        event_id="t0",
        corpus="earnings_sp500_2016_2025",
        ticker="ACN",
        event_date="2016-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        observed_outcomes={"direction": "neutral"},
    )
    result = {"final_risk": {"directional_pressure": 0.02, "drawdown_risk": 0.05}, "simulated_direction": "neutral"}
    score = score_event(event, result)
    assert score.direction_match is True


def test_score_event_direction_match():
    event = BenchmarkEvent(
        event_id="t1",
        corpus="earnings_sp500_2016_2025",
        ticker="NFLX",
        event_date="2022-04-19",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        observed_outcomes={"direction": "down"},
    )
    result = {"final_risk": {"directional_pressure": 0.4, "drawdown_risk": 0.5}, "dominant_causal_path": ["a"]}
    score = score_event(event, result)
    assert score.direction_match is True
    assert score.simulated_direction == "down"


def test_placebo_false_positive():
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
    score = score_event(event, result, placebo_drawdown_threshold=0.35, placebo_pressure_threshold=0.20)
    assert score.is_placebo is True
    assert score.false_positive is False


def test_scenario_replay_synthetic_earnings():
    event = BenchmarkEvent(
        event_id="TEST_2016Q1_earnings",
        corpus="earnings_sp500_2016_2025",
        ticker="TEST",
        event_date="2016-01-05",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        scenario_id="E1",
        observed_outcomes={"direction": "down", "after_hours_return_pct": -5.0},
        metadata={"synthetic_labels": True},
    )
    result = replay_scenario_event(event, until=60)
    assert "final_risk" in result
    assert result.get("simulated_direction") in {"down", "up", "neutral"}


def test_oot_split():
    events = [
        BenchmarkEvent("a", "c", "T", "2019-01-01", "e", "earnings", "scenario"),
        BenchmarkEvent("b", "c", "T", "2023-01-01", "e", "earnings", "scenario"),
    ]
    scores = [
        score_event(events[0], {"final_risk": {"directional_pressure": 0.2, "drawdown_risk": 0.4}, "simulated_direction": "down"}),
        score_event(events[1], {"final_risk": {"directional_pressure": 0.2, "drawdown_risk": 0.4}, "simulated_direction": "down"}),
    ]
    scores[0].observed_direction = "down"
    scores[0].direction_match = True
    scores[1].observed_direction = "up"
    scores[1].direction_match = False
    train, test = split_by_date(scores, events, cutoff_date="2022-01-01")
    oot = oot_accuracy(train, test)
    assert oot["train_n"] == 1
    assert oot["test_n"] == 1
    assert oot["train_direction_accuracy"] == 1.0
    assert oot["test_direction_accuracy"] == 0.0


def test_ablation_suite_runs():
    results = run_ablation_suite(["nflx_2022q1_earnings"], until=60)
    assert len(results) == 3
    summary = summarize_ablation(results)
    assert "no_news" in summary["by_channel"]


def test_load_events_default_corpora_includes_earnings():
    config = BenchmarkConfig(corpora=None, include_placebo=True, max_events_per_corpus=5)
    events = BenchmarkRunner(config).load_events()
    corpora = {e.corpus for e in events}
    assert "earnings_sp500_2016_2025" in corpora
    assert "placebo_quiet_days" in corpora


def test_benchmark_runner_smoke(tmp_path):
    config = BenchmarkConfig(
        corpora=["placebo_quiet_days", "macro_releases"],
        max_events_per_corpus=3,
        until=30,
        run_ablation=False,
        include_placebo=True,
        output_dir=tmp_path,
    )
    report = BenchmarkRunner(config).run()
    assert report["run_id"]
    assert Path(report["artifacts"]["json"]).exists()
    assert Path(report["artifacts"]["markdown"]).exists()
    assert Path(report["artifacts"]["human_review_csv"]).exists()
    payload = json.loads(Path(report["artifacts"]["json"]).read_text(encoding="utf-8"))
    assert payload["summary"]["count"] >= 3
