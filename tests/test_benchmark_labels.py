"""Tests for benchmark label enrichment."""

from __future__ import annotations

import json
from unittest.mock import patch

from market_causal_engine.benchmark.labels import (
    compute_earnings_return,
    enrich_event_record,
    _direction_from_return,
    _magnitude_bucket,
)


def test_direction_and_magnitude():
    assert _direction_from_return(2.0) == "up"
    assert _direction_from_return(-2.0) == "down"
    assert _direction_from_return(0.5) == "neutral"
    assert _magnitude_bucket(9.0) == "large"
    assert _magnitude_bucket(0.5) == "none"


def test_compute_earnings_return():
    bars = [
        {"time": "2022-04-18T00:00:00+00:00", "close": 100.0},
        {"time": "2022-04-19T00:00:00+00:00", "close": 75.0},
    ]
    label = compute_earnings_return(bars, "2022-04-19")
    assert label is not None
    assert label["direction"] == "down"
    assert label["after_hours_return_pct"] == -25.0


def test_enrich_event_record():
    record = {
        "event_id": "TEST",
        "ticker": "NFLX",
        "event_date": "2022-04-19",
        "metadata": {"synthetic_labels": True},
    }
    bars = [
        {"time": "2022-04-18T00:00:00+00:00", "close": 100.0},
        {"time": "2022-04-19T00:00:00+00:00", "close": 80.0},
    ]
    out = enrich_event_record(record, bars=bars)
    assert out["metadata"]["synthetic_labels"] is False
    assert out["observed_outcomes"]["direction"] == "down"
    assert out["scenario_id"] == "E1"
