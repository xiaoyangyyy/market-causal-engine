"""FRED/BLS macro ingestion with revision tracking."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_causal_engine.extraction.edgar_fetch import _user_agent
from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope, content_hash
from market_causal_engine.platform.storage.base import PlatformStore
from market_causal_engine.platform.storage.factory import get_platform_store

DEFAULT_FRED_SERIES = ("CPIAUCSL", "FEDFUNDS", "UNRATE")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fred_api_key() -> str | None:
    return os.environ.get("FRED_API_KEY") or os.environ.get("MARKET_CAUSAL_FRED_API_KEY")


def fetch_fred_observations(
    series_id: str,
    *,
    limit: int = 12,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    key = api_key or _fred_api_key()
    if not key:
        return []
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    url = "https://api.stlouisfed.org/fred/series/observations?" + urlencode(params)
    req = Request(url, headers={"User-Agent": _user_agent()})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out: list[dict[str, Any]] = []
    for obs in data.get("observations", []):
        if obs.get("value") in (".", None, ""):
            continue
        out.append(
            {
                "date": obs["date"],
                "value": float(obs["value"]),
                "revision_id": f"fred:{obs.get('realtime_start', obs['date'])}",
            }
        )
    return out


class FredBlsIngestor(Ingestor):
    """Ingest FRED series (with API key) and BLS/FOMC text releases with content-hash revisions."""

    source_kind = SourceKind.MACRO_FRED

    def __init__(self, *, store: PlatformStore | None = None, series: tuple[str, ...] = DEFAULT_FRED_SERIES) -> None:
        self.store = store or get_platform_store()
        self.series = series

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        result = IngestResult(source_kind=SourceKind.MACRO_FRED)

        # FRED numeric series
        for series_id in self.series:
            try:
                observations = fetch_fred_observations(series_id)
                result.fetched += len(observations)
                for obs in observations:
                    digest = content_hash({"series": series_id, "date": obs["date"], "value": obs["value"]})
                    inserted = self.store.upsert_macro_point(
                        series_id=series_id,
                        source="fred",
                        observation_date=obs["date"],
                        value=obs["value"],
                        revision_id=obs["revision_id"],
                        published_time=f"{obs['date']}T13:30:00+00:00",
                        content_hash=digest,
                    )
                    if not inserted and not ctx.force_refresh:
                        result.skipped += 1
                        continue
                    published = f"{obs['date']}T13:30:00+00:00"
                    if published > ctx.as_of_time:
                        result.skipped += 1
                        continue
                    record = PITRecord(
                        record_id=f"fred_{uuid.uuid4().hex[:12]}",
                        source_kind=SourceKind.MACRO_FRED,
                        source_id=f"fred:{series_id}:{obs['date']}",
                        payload={
                            "series_id": series_id,
                            "observation_date": obs["date"],
                            "value": obs["value"],
                        },
                        temporal=TemporalEnvelope(
                            observed_time=published,
                            published_time=published,
                            ingested_time=_utc_now_iso(),
                            revision_id=obs["revision_id"],
                        ),
                        metadata={"run_id": ctx.run_id},
                    )
                    result.records.append(record)
                    result.stored += 1
            except (HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
                result.errors.append(f"fred:{series_id}: {exc}")

        # BLS/FOMC text from case library (revision = content hash)
        from market_causal_engine.extraction.macro_fetch import list_macro_fetchable_cases, fetch_macro_for_case

        for case_id in list_macro_fetchable_cases():
            try:
                report = fetch_macro_for_case(case_id, overwrite=ctx.force_refresh)
                result.fetched += 1
                root_text_path = report.get("output_path")
                if not root_text_path:
                    continue
                from pathlib import Path

                text = Path(root_text_path).read_text(encoding="utf-8")
                digest = content_hash(text[:5000])
                source = str(report.get("source", "macro"))
                event_date = str(report.get("event_date") or report.get("release_date", ctx.as_of_time[:10]))
                series_id = f"bls_cpi:{event_date}" if source == "bls_cpi" else f"fomc:{event_date}"
                kind = SourceKind.MACRO_BLS if source == "bls_cpi" else SourceKind.MACRO_FOMC
                revision_id = digest[:16]
                inserted = self.store.upsert_macro_point(
                    series_id=series_id,
                    source=source,
                    observation_date=event_date,
                    value=None,
                    revision_id=revision_id,
                    published_time=f"{event_date}T14:00:00+00:00",
                    content_hash=digest,
                    metadata={"case_id": case_id, "text_length": len(text)},
                )
                published = f"{event_date}T14:00:00+00:00"
                if published > ctx.as_of_time:
                    result.skipped += 1
                    continue
                if not inserted and not ctx.force_refresh:
                    result.skipped += 1
                    continue
                record = PITRecord(
                    record_id=f"macro_{uuid.uuid4().hex[:12]}",
                    source_kind=kind,
                    source_id=f"{source}:{case_id}",
                    payload={
                        "case_id": case_id,
                        "source": source,
                        "text_length": len(text),
                        "text_preview": text[:400],
                        "content_hash": digest,
                    },
                    temporal=TemporalEnvelope(
                        observed_time=published,
                        published_time=published,
                        ingested_time=_utc_now_iso(),
                        revision_id=revision_id,
                    ),
                    metadata={"run_id": ctx.run_id},
                )
                result.records.append(record)
                result.stored += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"macro_case:{case_id}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
