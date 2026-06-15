"""Macro release ingestion adapter — FOMC/CPI from case library + live fetch."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _macro_case_ids() -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "case_studies"
    out: list[str] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if data.get("domain") == "macro" or data.get("event_type") in ("fomc", "cpi"):
            out.append(data.get("case_id", manifest_path.parent.name))
    return out


class MacroIngestor(Ingestor):
    source_kind = SourceKind.MACRO_FOMC

    def __init__(self, *, case_ids: list[str] | None = None) -> None:
        self._case_ids = case_ids or _macro_case_ids()

    def ingest(self, ctx: IngestContext) -> IngestResult:
        from market_causal_engine.extraction.macro_fetch import fetch_macro_for_case

        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)

        for case_id in self._case_ids:
            try:
                fetch_result = fetch_macro_for_case(case_id, overwrite=ctx.force_refresh)
                result.fetched += 1
                root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "case_studies" / case_id
                manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
                event_date = str(
                    fetch_result.get("event_date")
                    or fetch_result.get("release_date")
                    or manifest.get("event_date", ctx.as_of_time[:10])
                )
                source = str(fetch_result.get("source", manifest.get("event_type", "macro")))
                published = f"{event_date}T14:00:00+00:00"

                kind = SourceKind.MACRO_FOMC if source == "fomc" else SourceKind.MACRO_BLS
                record = PITRecord(
                    record_id=f"macro_{uuid.uuid4().hex[:12]}",
                    source_kind=kind,
                    source_id=f"{source}:{case_id}",
                    payload={
                        "case_id": case_id,
                        "source": source,
                        "text_length": fetch_result.get("text_length", 0),
                        "output_path": fetch_result.get("output_path"),
                    },
                    temporal=TemporalEnvelope(
                        observed_time=published,
                        published_time=published,
                        ingested_time=_utc_now_iso(),
                        revision_id=f"{source}:{event_date}",
                    ),
                    metadata={"run_id": ctx.run_id},
                )
                result.records.append(record)
                result.stored += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{case_id}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
