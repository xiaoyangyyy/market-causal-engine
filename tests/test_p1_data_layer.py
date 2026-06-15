"""P1 data layer tests — filing diff, news merge, backfill, market parse."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from market_causal_engine.platform.backfill import BackfillRunner
from market_causal_engine.platform.ingestion.base import IngestContext, IngestResult
from market_causal_engine.platform.ingestion.market_prices import MarketPricesIngestor, _parse_bars
from market_causal_engine.platform.ingestion.news_merge import NewsMergedIngestor, _dedupe_key
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope
from market_causal_engine.platform.provenance import new_run_id
from market_causal_engine.platform.registry import FilingVersion
from market_causal_engine.platform.storage.local import LocalPlatformStore
from market_causal_engine.platform.watchlist import load_watchlist, sector_etf_for


def test_filing_diff_detection(tmp_path):
    store = LocalPlatformStore(tmp_path)
    f1 = FilingVersion(
        ticker="NFLX",
        accession_number="0001065280-22-000012",
        form_type="8-K",
        filing_date="2022-04-19",
        content_hash="sha256:aaa",
    )
    v1 = store.upsert_filing(f1)
    assert v1.changed is True
    assert v1.is_amended is False

    v2 = store.upsert_filing(
        FilingVersion(
            ticker="NFLX",
            accession_number="0001065280-22-000012",
            form_type="8-K",
            filing_date="2022-04-19",
            content_hash="sha256:aaa",
        )
    )
    assert v2.changed is False

    v3 = store.upsert_filing(
        FilingVersion(
            ticker="NFLX",
            accession_number="0001065280-22-000012",
            form_type="8-K",
            filing_date="2022-04-19",
            content_hash="sha256:bbb",
        )
    )
    assert v3.changed is True
    assert v3.is_amended is True


def test_macro_revision_storage(tmp_path):
    store = LocalPlatformStore(tmp_path)
    assert store.upsert_macro_point(
        series_id="CPIAUCSL",
        source="fred",
        observation_date="2024-01-01",
        value=3.1,
        revision_id="fred:2024-01-01",
        published_time="2024-01-01T13:30:00+00:00",
        content_hash="h1",
    )
    assert not store.upsert_macro_point(
        series_id="CPIAUCSL",
        source="fred",
        observation_date="2024-01-01",
        value=3.1,
        revision_id="fred:2024-01-01",
        published_time="2024-01-01T13:30:00+00:00",
        content_hash="h1",
    )
    revs = store.list_macro_revisions("CPIAUCSL")
    assert len(revs) == 1


def test_news_merge_dedupes():
    t = TemporalEnvelope.now()
    r1 = PITRecord("a1", SourceKind.NEWS_API, "id1", {"title": "Apple beats", "url": "http://x"}, t)
    r2 = PITRecord("a2", SourceKind.NEWS_RSS, "id2", {"title": "Apple beats", "url": "http://x"}, t)
    assert _dedupe_key(r1) == _dedupe_key(r2)

    rss = MagicMock()
    rss.ingest.return_value = IngestResult(SourceKind.NEWS_RSS, records=[r2], stored=1, fetched=1)
    api = MagicMock()
    api.ingest.return_value = IngestResult(SourceKind.NEWS_API, records=[r1], stored=1, fetched=1)

    ingestor = NewsMergedIngestor(rss=rss, newsapi=api)
    ctx = IngestContext(run_id=new_run_id("t"), as_of_time="2099-01-01T00:00:00+00:00")
    result = ingestor.ingest(ctx)
    assert result.stored == 1
    assert result.skipped == 1


def test_parse_yahoo_bars():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD"},
                    "timestamp": [1700000000, 1700086400],
                    "indicators": {"quote": [{"close": [100.0, 101.5], "volume": [1e6, 1.1e6]}]},
                }
            ]
        }
    }
    bars = _parse_bars(payload)
    assert len(bars) == 2
    assert bars[1]["close"] == 101.5


def test_market_prices_ingest_mocked():
    chart = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD"},
                    "timestamp": [1700000000],
                    "indicators": {"quote": [{"close": [50.0], "volume": [1000]}]},
                }
            ]
        }
    }
    ingestor = MarketPricesIngestor(watchlist={"tickers": ["TEST"], "sector_etfs": {"TEST": "SPY", "DEFAULT": "SPY"}})
    ctx = IngestContext(run_id=new_run_id("t"), as_of_time="2099-01-01T00:00:00+00:00", tickers=["TEST"])
    with patch("market_causal_engine.platform.ingestion.market_prices._yahoo_chart", return_value=chart):
        result = ingestor.ingest(ctx)
    assert result.stored >= 1
    assert result.records[0].payload["ticker"] == "TEST"
    assert result.records[0].payload["options_iv"]["stub"] is True


def test_backfill_macro_job(tmp_path):
    store = LocalPlatformStore(tmp_path)
    runner = BackfillRunner(store)

    mock_result = IngestResult(SourceKind.MACRO_FRED, stored=2, fetched=2)

    with patch.object(
        __import__("market_causal_engine.platform.ingestion.fred_bls", fromlist=["FredBlsIngestor"]).FredBlsIngestor,
        "ingest",
        return_value=mock_result,
    ):
        job = runner.start("macro_fred")
    assert job.status == "succeeded"
    assert job.completed == 2
    loaded = store.get_job(job.job_id)
    assert loaded is not None
    assert loaded.status == "succeeded"


def test_backfill_resume(tmp_path):
    store = LocalPlatformStore(tmp_path)
    runner = BackfillRunner(store)
    mock_result = IngestResult(SourceKind.MACRO_FRED, stored=1, fetched=1)
    with patch.object(
        __import__("market_causal_engine.platform.ingestion.fred_bls", fromlist=["FredBlsIngestor"]).FredBlsIngestor,
        "ingest",
        return_value=mock_result,
    ):
        job = runner.start("macro_fred")
        job.status = "failed"
        job.error = "simulated"
        store.update_job(job)
        resumed = runner.start("macro_fred", resume_job_id=job.job_id)
    assert resumed.job_id == job.job_id
    assert resumed.status == "succeeded"


def test_watchlist_loader():
    wl = load_watchlist()
    assert "tickers" in wl
    assert sector_etf_for("NFLX", wl) in ("XLC", "SPY")


def test_fetch_fred_observations_empty_without_key():
    from market_causal_engine.platform.ingestion.fred_bls import fetch_fred_observations

    with patch.dict("os.environ", {}, clear=True):
        assert fetch_fred_observations("CPIAUCSL") == []


def test_fetch_fred_observations_parsed():
    from market_causal_engine.platform.ingestion.fred_bls import fetch_fred_observations

    payload = json.dumps(
        {"observations": [{"date": "2024-01-01", "value": "3.1", "realtime_start": "2024-01-01"}]}
    ).encode()

    with patch.dict("os.environ", {"FRED_API_KEY": "testkey"}):
        with patch("market_causal_engine.platform.ingestion.fred_bls.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = payload
            obs = fetch_fred_observations("CPIAUCSL", api_key="testkey")
    assert obs[0]["value"] == 3.1
