"""SEC EDGAR ingestion adapter — wraps case-study fetch with PIT envelope."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _case_studies_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "case_studies"


class SecEdgarIngestor(Ingestor):
    """Poll EDGAR for configured case-study tickers (dev: case library as watchlist)."""

    source_kind = SourceKind.SEC_EDGAR

    def __init__(self, *, case_ids: list[str] | None = None) -> None:
        self._case_ids = case_ids

    def _resolve_case_ids(self, ctx: IngestContext) -> list[str]:
        if self._case_ids:
            return self._case_ids
        root = _case_studies_root()
        ids: list[str] = []
        for manifest in sorted(root.glob("*/manifest.json")):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            src_path = manifest.parent / "sources" / "sources.json"
            if src_path.exists():
                src = json.loads(src_path.read_text(encoding="utf-8"))
                if src.get("edgar"):
                    ids.append(data.get("case_id", manifest.parent.name))
        if ctx.tickers:
            ticker_set = {t.upper() for t in ctx.tickers}
            filtered = []
            for cid in ids:
                manifest = json.loads((_case_studies_root() / cid / "manifest.json").read_text(encoding="utf-8"))
                if str(manifest.get("ticker", "")).upper() in ticker_set:
                    filtered.append(cid)
            return filtered or ids
        return ids

    def ingest(self, ctx: IngestContext) -> IngestResult:
        from market_causal_engine.extraction.edgar_fetch import fetch_edgar_for_case

        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)
        case_ids = self._resolve_case_ids(ctx)

        for case_id in case_ids:
            try:
                fetch_result = fetch_edgar_for_case(case_id, overwrite=ctx.force_refresh)
                result.fetched += 1
                manifest_path = _case_studies_root() / case_id / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                ticker = str(fetch_result.get("ticker") or manifest.get("ticker", case_id))
                event_date = str(fetch_result.get("event_date") or manifest.get("event_date", ctx.as_of_time[:10]))

                published = f"{event_date}T21:00:00+00:00"
                record = PITRecord(
                    record_id=f"sec_{uuid.uuid4().hex[:12]}",
                    source_kind=SourceKind.SEC_EDGAR,
                    source_id=f"{ticker}:8-K:{case_id}",
                    payload={
                        "case_id": case_id,
                        "ticker": ticker,
                        "form_type": "8-K",
                        "accession": fetch_result.get("accession_number"),
                        "filing_url": fetch_result.get("document_url"),
                        "text_length": fetch_result.get("text_length", 0),
                    },
                    temporal=TemporalEnvelope(
                        observed_time=published,
                        published_time=published,
                        ingested_time=_utc_now_iso(),
                        revision_id=str(fetch_result.get("accession_number", "initial")),
                    ),
                    metadata={"run_id": ctx.run_id},
                )
                result.records.append(record)
                result.stored += 1
            except Exception as exc:  # noqa: BLE001 — ingestion must collect, not abort
                result.errors.append(f"{case_id}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
