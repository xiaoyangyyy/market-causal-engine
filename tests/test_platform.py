"""Tests for production platform layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from market_causal_engine.platform.ingestion.base import IngestContext, IngestResult
from market_causal_engine.platform.ingestion.news_rss import NewsRssIngestor, _parse_rss_date
from market_causal_engine.platform.pipeline import DailyPipeline
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope, content_hash
from market_causal_engine.platform.provenance import RunManifest, new_run_id, trace_determinism_hash
from market_causal_engine.platform.quality import validate_pit_record, validate_records
from market_causal_engine.platform.storage.local import LocalStorageBackend


def test_pit_record_content_hash_stable():
    temporal = TemporalEnvelope.now(observed="2022-04-19T21:00:00+00:00", published="2022-04-19T21:00:00+00:00")
    r1 = PITRecord(
        record_id="r1",
        source_kind=SourceKind.SEC_EDGAR,
        source_id="NFLX:8-K:test",
        payload={"ticker": "NFLX"},
        temporal=temporal,
    )
    r2 = PITRecord(
        record_id="r2",
        source_kind=SourceKind.SEC_EDGAR,
        source_id="NFLX:8-K:test",
        payload={"ticker": "NFLX"},
        temporal=temporal,
    )
    assert r1.content_hash == r2.content_hash
    assert r1.content_hash.startswith("sha256:")


def test_admissible_at():
    temporal = TemporalEnvelope(
        observed_time="2022-04-19T21:00:00+00:00",
        published_time="2022-04-19T21:00:00+00:00",
        ingested_time="2022-04-20T08:00:00+00:00",
    )
    rec = PITRecord(
        record_id="r1",
        source_kind=SourceKind.NEWS_RSS,
        source_id="news:1",
        payload={"title": "test"},
        temporal=temporal,
    )
    assert rec.admissible_at("2022-04-20T00:00:00+00:00")
    assert not rec.admissible_at("2022-04-19T20:00:00+00:00")


def test_quality_rejects_lookahead():
    rec = PITRecord(
        record_id="r1",
        source_kind=SourceKind.NEWS_RSS,
        source_id="news:1",
        payload={"title": "x"},
        temporal=TemporalEnvelope(
            observed_time="2022-04-20T12:00:00+00:00",
            published_time="2022-04-20T12:00:00+00:00",
            ingested_time="2022-04-20T12:00:00+00:00",
        ),
    )
    issues = validate_pit_record(rec, as_of_time="2022-04-19T12:00:00+00:00")
    assert any(i.code == "lookahead_violation" for i in issues)


def test_local_storage_roundtrip(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    temporal = TemporalEnvelope.now()
    rec = PITRecord(
        record_id="r1",
        source_kind=SourceKind.MANUAL,
        source_id="manual:1",
        payload={"k": "v"},
        temporal=temporal,
    )
    snap = "snap_test"
    assert storage.save_records(snap, [rec]) == 1
    loaded = storage.list_records(snapshot_id=snap)
    assert len(loaded) == 1
    assert loaded[0].source_id == "manual:1"


def test_run_manifest_save_load(tmp_path):
    m = RunManifest(run_id=new_run_id("test"))
    m.add_stage("ingest", status="ok")
    path = tmp_path / "run.json"
    m.save(path)
    loaded = RunManifest.load(path)
    assert loaded.run_id == m.run_id
    assert len(loaded.stages) == 1


def test_daily_pipeline_offline(tmp_path):
    pipeline = DailyPipeline(store_root=tmp_path, ingestors=[])
    result = pipeline.run(
        as_of_time="2026-06-05T08:00:00+00:00",
        skip_network_ingest=True,
        replay_cases=True,
    )
    assert result.status == "succeeded"
    assert result.snapshot_id.startswith("snap_")
    assert len(result.event_cards) >= 1


def test_trace_determinism_hash():
    trace = [{"time": 1, "kind": "a", "action": "executed"}]
    assert trace_determinism_hash(trace) == trace_determinism_hash(list(trace))


def test_parse_rss_date_fallback():
    assert _parse_rss_date(None)
    assert _parse_rss_date("not-a-date")


def test_metrics_registry():
    from market_causal_engine.observability.metrics import REGISTRY

    REGISTRY.inc("test_counter_total")
    text = REGISTRY.render_prometheus()
    assert "test_counter_total" in text


@pytest.mark.skipif(
    True,
    reason="Network RSS test — run manually with MARKET_CAUSAL_LIVE=1",
)
def test_news_rss_live():
    ingestor = NewsRssIngestor(max_items_per_feed=1)
    ctx = IngestContext(run_id=new_run_id("test"), as_of_time=datetime.now(timezone.utc).isoformat())
    result = ingestor.ingest(ctx)
    assert isinstance(result, IngestResult)
