"""NewsAPI ingestion adapter."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_causal_engine.extraction.edgar_fetch import _user_agent
from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope
from market_causal_engine.platform.watchlist import load_watchlist


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _newsapi_key() -> str | None:
    return os.environ.get("NEWSAPI_KEY") or os.environ.get("MARKET_CAUSAL_NEWSAPI_KEY")


def fetch_newsapi_headlines(
    query: str,
    *,
    api_key: str | None = None,
    from_days: int = 3,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    key = api_key or _newsapi_key()
    if not key:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=from_days)).date().isoformat()
    params = {
        "q": query,
        "from": since,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "language": "en",
        "apiKey": key,
    }
    url = "https://newsapi.org/v2/everything?" + urlencode(params)
    req = Request(url, headers={"User-Agent": _user_agent()})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return list(data.get("articles", []))


class NewsApiIngestor(Ingestor):
    source_kind = SourceKind.NEWS_API

    def __init__(self, *, watchlist: dict[str, Any] | None = None, page_size: int = 5) -> None:
        self.watchlist = watchlist or load_watchlist()
        self.page_size = page_size

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)
        if not _newsapi_key():
            result.errors.append("NEWSAPI_KEY not set — skipping NewsAPI")
            result.duration_ms = (time.monotonic() - t0) * 1000
            return result

        tickers = ctx.tickers or list(self.watchlist.get("tickers", []))
        queries = tickers[:5] if tickers else ["earnings", "Federal Reserve"]

        for query in queries:
            try:
                articles = fetch_newsapi_headlines(query, page_size=self.page_size)
                result.fetched += len(articles)
                for art in articles:
                    published_raw = art.get("publishedAt") or _utc_now_iso()
                    published = published_raw.replace("Z", "+00:00")
                    if published > ctx.as_of_time:
                        result.skipped += 1
                        continue
                    title = str(art.get("title") or "")
                    if not title or title == "[Removed]":
                        result.skipped += 1
                        continue
                    record = PITRecord(
                        record_id=f"newsapi_{uuid.uuid4().hex[:12]}",
                        source_kind=SourceKind.NEWS_API,
                        source_id=f"newsapi:{art.get('url', title[:40])}",
                        payload={
                            "query": query,
                            "title": title,
                            "url": art.get("url"),
                            "source_name": (art.get("source") or {}).get("name"),
                            "description": (art.get("description") or "")[:500],
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
            except (HTTPError, URLError, json.JSONDecodeError) as exc:
                result.errors.append(f"newsapi:{query}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
