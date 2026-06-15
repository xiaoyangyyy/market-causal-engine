"""RSS news ingestion — public feeds as first production news source."""

from __future__ import annotations

import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope

# Default public RSS feeds (no API key required)
DEFAULT_FEEDS: dict[str, str] = {
    "sec_press": "https://www.sec.gov/news/pressreleases.rss",
    "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_rss_date(raw: str | None) -> str:
    if not raw:
        return _utc_now_iso()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OverflowError):
        return _utc_now_iso()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _fetch_rss(url: str, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    req = Request(url, headers={"User-Agent": "MarketCausalEngine/0.4 (research)"})
    with urlopen(req, timeout=timeout) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    items: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        pub = item.findtext("pubDate")
        if title:
            items.append({"title": title, "link": link, "summary": desc[:500], "pubDate": pub})
    return items


class NewsRssIngestor(Ingestor):
    """Fetch recent headlines from configured RSS feeds."""

    source_kind = SourceKind.NEWS_RSS

    def __init__(self, feeds: dict[str, str] | None = None, *, max_items_per_feed: int = 10) -> None:
        self._feeds = feeds or DEFAULT_FEEDS
        self._max_items = max_items_per_feed

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)

        for feed_name, url in self._feeds.items():
            try:
                items = _fetch_rss(url)
                result.fetched += len(items)
                for item in items[: self._max_items]:
                    published = _parse_rss_date(item.get("pubDate"))
                    if published > ctx.as_of_time:
                        result.skipped += 1
                        continue
                    record = PITRecord(
                        record_id=f"news_{uuid.uuid4().hex[:12]}",
                        source_kind=SourceKind.NEWS_RSS,
                        source_id=f"rss:{feed_name}:{item.get('link', item['title'][:40])}",
                        payload={
                            "feed": feed_name,
                            "title": item["title"],
                            "link": item.get("link", ""),
                            "summary": item.get("summary", ""),
                        },
                        temporal=TemporalEnvelope(
                            observed_time=published,
                            published_time=published,
                            ingested_time=_utc_now_iso(),
                        ),
                        metadata={"run_id": ctx.run_id},
                    )
                    result.records.append(record)
                    result.stored += 1
            except (URLError, ET.ParseError, TimeoutError) as exc:
                result.errors.append(f"{feed_name}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
