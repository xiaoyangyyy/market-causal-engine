"""Merged news ingestion: RSS + NewsAPI with deduplication."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.ingestion.news_api import NewsApiIngestor
from market_causal_engine.platform.ingestion.news_rss import NewsRssIngestor
from market_causal_engine.platform.pit import PITRecord, SourceKind


def _dedupe_key(record: PITRecord) -> str:
    title = str(record.payload.get("title", "")).lower().strip()
    link = str(record.payload.get("link") or record.payload.get("url") or "")
    raw = f"{title}|{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class NewsMergedIngestor(Ingestor):
    """Combine RSS and NewsAPI sources with priority: NewsAPI > RSS on duplicate titles."""

    source_kind = SourceKind.NEWS_RSS

    def __init__(
        self,
        *,
        rss: NewsRssIngestor | None = None,
        newsapi: NewsApiIngestor | None = None,
    ) -> None:
        self.rss = rss or NewsRssIngestor(max_items_per_feed=8)
        self.newsapi = newsapi or NewsApiIngestor(page_size=5)

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        merged = IngestResult(source_kind=self.source_kind)
        seen: dict[str, PITRecord] = {}

        for ingestor in (self.newsapi, self.rss):
            partial = ingestor.ingest(ctx)
            merged.fetched += partial.fetched
            merged.errors.extend(partial.errors)
            for record in partial.records:
                key = _dedupe_key(record)
                if key in seen:
                    merged.skipped += 1
                    continue
                seen[key] = record

        merged.records = list(seen.values())
        merged.stored = len(merged.records)
        merged.duration_ms = (time.monotonic() - t0) * 1000
        return merged
