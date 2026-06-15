"""Tests for catalog feed replay and IPO corpus cleaning."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from market_causal_engine.benchmark.catalog.fetch import build_atoms_for_event
from market_causal_engine.benchmark.catalog.ipo import classify_exclusion, first_trading_date
from market_causal_engine.benchmark.catalog.replay import has_catalog_atoms, replay_catalog_feed_event
from market_causal_engine.benchmark.catalog.store import catalog_event_dir
from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.replay import replay_event


SAMPLE_8K = (
    "Item 2.02 Results of Operations and Financial Condition. "
    "On April 19, 2022, Netflix, Inc. announced financial results for the quarter ended March 31, 2022. "
    "The company reported a net loss of 200,000 paid memberships in Q1 versus consensus expectations "
    "for a gain of approximately 2.5 million subscribers. "
    "Revenue grew 9.8 percent year over year but missed analyst expectations. "
    "The company expects Q2 revenue growth to slow and projects a loss of 2 million subscribers."
)


@pytest.fixture
def catalog_event(tmp_path, monkeypatch):
    from market_causal_engine.benchmark import catalog as catalog_pkg
    from market_causal_engine.benchmark.catalog import store

    monkeypatch.setattr(store, "CATALOG_ROOT", tmp_path / "catalog")
    monkeypatch.setattr(catalog_pkg.store, "CATALOG_ROOT", tmp_path / "catalog")

    event = BenchmarkEvent(
        event_id="NFLX_2022Q1_earnings",
        corpus="earnings_sp500_2016_2025",
        ticker="NFLX",
        event_date="2022-04-19",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        fiscal_period="2022Q1",
        observed_outcomes={"direction": "down", "after_hours_return_pct": -25.0},
        labels={"is_major_event": True},
    )
    build_atoms_for_event(event, offline_text=SAMPLE_8K)
    return event


def test_first_trading_date_and_pre_ipo():
    bars = [{"time": "2020-12-10", "close": 100}, {"time": "2021-01-04", "close": 101}]
    assert first_trading_date(bars) == "2020-12-10"
    record = {"ticker": "ABNB", "event_date": "2016-01-05", "metadata": {}}
    assert classify_exclusion(record, bars=bars) == "pre_ipo"
    record_ok = {"ticker": "ABNB", "event_date": "2021-01-04", "metadata": {}}
    bars_with_prev = [
        {"time": "2020-12-31", "close": 100},
        {"time": "2021-01-04", "close": 101, "open": 101},
    ]
    assert classify_exclusion(record_ok, bars=bars_with_prev) is None


def test_unpriceable_weekend_date():
    bars = [
        {"time": "2016-07-07", "close": 10, "open": 10},
        {"time": "2016-07-08", "close": 10, "open": 10},
        {"time": "2016-07-11", "close": 10, "open": 10},
    ]
    record = {"ticker": "AMD", "event_date": "2016-07-09", "metadata": {}}
    assert classify_exclusion(record, bars=bars) == "unpriceable_date"


def test_catalog_queue_prioritizes_benchmark_sample():
    from market_causal_engine.benchmark.catalog.queue import (
        benchmark_sample_event_ids,
        catalog_coverage_stats,
        prioritize_catalog_events,
    )
    from market_causal_engine.benchmark.models import BenchmarkEvent

    sample = benchmark_sample_event_ids(max_events=20, seed=1)
    assert len(sample) == 20
    ev_a = BenchmarkEvent(
        event_id="AAA",
        corpus="x",
        ticker="A",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
    )
    ev_b = BenchmarkEvent(
        event_id=list(sample)[0],
        corpus="x",
        ticker="B",
        event_date="2020-01-02",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        labels={"is_major_event": True},
    )
    ordered = prioritize_catalog_events([ev_a, ev_b], benchmark_first=True)
    assert ordered[0].event_id == ev_b.event_id
    stats = catalog_coverage_stats(benchmark_max=50)
    assert stats["corpus_total"] > 100


def test_edgar_earnings_scoring_penalizes_proxy_filings():
    from market_causal_engine.extraction.edgar_fetch import _score_earnings_package

    earnings = _score_earnings_package(
        "Item 2.02 Results of Operations. The company reported quarterly revenue and EPS.",
        "Exhibit 99.1 earnings release",
    )
    proxy = _score_earnings_package(
        "Item 5.07 Submission of matters to a vote of security holders at annual meeting.",
        None,
    )
    assert earnings > proxy


def test_historical_cik_for_blk_and_avgo():
    from market_causal_engine.benchmark.catalog.cik_resolver import (
        candidate_ciks_for_event,
        resolve_cik_for_event,
    )

    assert resolve_cik_for_event("BLK", "2016-07-07") == "0001364742"
    assert resolve_cik_for_event("BLK", "2024-01-11") == "0001364742"
    assert resolve_cik_for_event("BLK", "2025-01-01") == "0002012383"
    assert resolve_cik_for_event("AVGO", "2016-10-05") == "0001649338"
    assert resolve_cik_for_event("DIS", "2017-07-11") == "0001001039"
    assert resolve_cik_for_event("DIS", "2019-01-16") == "0001744489"
    assert "0001001039" in candidate_ciks_for_event("DIS", "2019-01-16")


def test_fiscal_period_date_range():
    from market_causal_engine.benchmark.catalog.fiscal import fiscal_period_date_range

    assert fiscal_period_date_range("2022Q1") == ("2022-04-01", "2022-05-31")
    assert fiscal_period_date_range("2022Q4") == ("2023-01-01", "2023-02-28")


def test_build_atoms_offline(catalog_event):
    assert has_catalog_atoms(catalog_event.event_id)
    manifest_path = catalog_event_dir(catalog_event.event_id) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["atom_count"] >= 1


def test_catalog_feed_replay(catalog_event):
    result = replay_catalog_feed_event(catalog_event, until=60)
    assert result["replay_mode"] == "catalog_feed"
    assert "final_risk" in result
    assert result.get("simulated_direction") in {"down", "up", "neutral"}
    assert result["catalog_admissible_count"] >= 1


def test_replay_event_routes_via_learned_stack(catalog_event):
    from market_causal_engine.benchmark.catalog.claims import extract_claims_for_catalog_event

    extract_claims_for_catalog_event(catalog_event, write=True)
    result = replay_event(catalog_event, until=60)
    assert result["replay_mode"] in {"catalog_feed", "scenario"}
    if result["replay_mode"] == "scenario":
        assert result.get("catalog_fallback") is True


def test_replay_event_falls_back_without_atoms():
    event = BenchmarkEvent(
        event_id="NOATOMS_2020Q1_earnings",
        corpus="earnings_sp500_2016_2025",
        ticker="ZZZZ",
        event_date="2020-01-15",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        scenario_id="E1",
        observed_outcomes={"direction": "down"},
    )
    result = replay_event(event, until=30)
    assert result["replay_mode"] == "scenario"
