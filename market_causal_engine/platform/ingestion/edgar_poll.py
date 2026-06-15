"""EDGAR polling ingestor with filing diff detection."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from market_causal_engine.extraction.edgar_fetch import fetch_filing_text, list_recent_filings
from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope, content_hash
from market_causal_engine.platform.registry import FilingVersion
from market_causal_engine.platform.storage.base import PlatformStore
from market_causal_engine.platform.storage.factory import get_platform_store
from market_causal_engine.platform.watchlist import load_watchlist


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EdgarPollIngestor(Ingestor):
    """Poll SEC EDGAR for watchlist tickers; emit PIT records only for new/changed filings."""

    source_kind = SourceKind.SEC_EDGAR

    def __init__(
        self,
        *,
        store: PlatformStore | None = None,
        watchlist: dict[str, Any] | None = None,
    ) -> None:
        self.store = store or get_platform_store()
        self.watchlist = watchlist or load_watchlist()

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)
        tickers = ctx.tickers or list(self.watchlist.get("tickers", []))
        forms = tuple(self.watchlist.get("edgar_forms", ["8-K"]))
        lookback = int(self.watchlist.get("poll_lookback_days", 30))

        for ticker in tickers:
            try:
                filings = list_recent_filings(ticker, lookback_days=lookback, forms=forms)
                result.fetched += len(filings)
                for filing in filings:
                    text = fetch_filing_text(filing)
                    if len(text) > 80_000:
                        text = text[:80_000]
                    digest = content_hash(text)
                    version = self.store.upsert_filing(
                        FilingVersion(
                            ticker=ticker.upper(),
                            accession_number=filing.accession_number,
                            form_type=filing.form,
                            filing_date=filing.filing_date,
                            content_hash=digest,
                            document_url=filing.document_url(),
                        )
                    )
                    if not version.changed and not ctx.force_refresh:
                        result.skipped += 1
                        continue

                    published = f"{filing.filing_date}T21:00:00+00:00"
                    if published > ctx.as_of_time:
                        result.skipped += 1
                        continue

                    record = PITRecord(
                        record_id=f"sec_{uuid.uuid4().hex[:12]}",
                        source_kind=SourceKind.SEC_EDGAR,
                        source_id=f"{ticker.upper()}:{filing.form}:{filing.accession_number}",
                        payload={
                            "ticker": ticker.upper(),
                            "form_type": filing.form,
                            "accession_number": filing.accession_number,
                            "filing_date": filing.filing_date,
                            "document_url": filing.document_url(),
                            "text_length": len(text),
                            "text_preview": text[:500],
                            "is_amended": version.is_amended,
                            "changed": version.changed,
                        },
                        temporal=TemporalEnvelope(
                            observed_time=published,
                            published_time=published,
                            ingested_time=_utc_now_iso(),
                            revision_id=filing.accession_number,
                        ),
                        metadata={"run_id": ctx.run_id, "poll": True},
                    )
                    result.records.append(record)
                    result.stored += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{ticker}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
