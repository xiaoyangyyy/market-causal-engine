"""Tests for benchmark label tier classification."""

from __future__ import annotations

from market_causal_engine.benchmark.label_quality import is_real_label, label_tier
from market_causal_engine.benchmark.metrics import build_headline_summary, naive_baselines, score_event
from market_causal_engine.benchmark.models import BenchmarkEvent


def test_label_tier_real_yahoo():
    event = BenchmarkEvent(
        event_id="x",
        corpus="earnings_sp500_2016_2025",
        ticker="NFLX",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        metadata={"label_source": "yahoo_daily", "synthetic_labels": False},
    )
    assert label_tier(event) == "real"
    assert is_real_label(event)


def test_label_tier_proxy():
    event = BenchmarkEvent(
        event_id="x",
        corpus="earnings_sp500_2016_2025",
        ticker="X",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        metadata={"synthetic_labels": True},
    )
    assert label_tier(event) == "proxy"


def test_headline_excludes_proxy_from_real_accuracy():
    real_ev = BenchmarkEvent(
        event_id="r",
        corpus="earnings_sp500_2016_2025",
        ticker="A",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        observed_outcomes={"direction": "up"},
        metadata={"label_source": "yahoo_daily", "synthetic_labels": False},
    )
    proxy_ev = BenchmarkEvent(
        event_id="p",
        corpus="earnings_sp500_2016_2025",
        ticker="B",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        observed_outcomes={"direction": "down"},
        metadata={"synthetic_labels": True},
    )
    scores = [
        score_event(real_ev, {"final_risk": {}, "simulated_direction": "up", "replay_mode": "scenario"}),
        score_event(proxy_ev, {"final_risk": {}, "simulated_direction": "up", "replay_mode": "scenario"}),
    ]
    headline = build_headline_summary(scores)
    assert headline["real_label_n"] == 1
    assert headline["real_label_direction_accuracy"] == 1.0
    assert headline["proxy_label_n"] == 1


def test_naive_baselines():
    events = [
        BenchmarkEvent(
            event_id=f"e{i}",
            corpus="c",
            ticker="T",
            event_date="2020-01-01",
            event_type="e",
            domain="earnings",
            replay_mode="scenario",
            observed_outcomes={"direction": d},
            metadata={"label_source": "yahoo_daily"},
        )
        for i, d in enumerate(["neutral", "neutral", "up"])
    ]
    scores = [
        score_event(ev, {"final_risk": {}, "simulated_direction": "down", "replay_mode": "scenario"})
        for ev in events
    ]
    base = naive_baselines(scores, label_tier="real")
    assert base["always_neutral_accuracy"] == round(2 / 3, 4)
