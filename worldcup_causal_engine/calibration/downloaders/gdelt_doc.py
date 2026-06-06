"""GDELT DOC 2.0 timeline fetcher (public, no API key)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_timeline_volume(
    query: str,
    *,
    start: str,
    end: str,
    cache_path: str | Path | None = None,
    retries: int = 4,
    sleep_s: float = 8.0,
) -> dict[str, Any]:
    """Fetch timelinevolraw JSON; cache to disk to respect rate limits."""
    cache = Path(cache_path) if cache_path else None
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    params = {
        "query": query,
        "mode": "timelinevolraw",
        "format": "json",
        "STARTDATETIME": start,
        "ENDDATETIME": end,
    }
    url = f"{GDELT_DOC_API}?{urlencode(params)}"

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=90) as resp:
                data = json.loads(resp.read())
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries - 1:
                time.sleep(sleep_s * (attempt + 1))
                continue
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(sleep_s)
                continue
            raise

    raise RuntimeError(f"GDELT fetch failed: {last_err}")


def timeline_stats(data: dict[str, Any]) -> dict[str, Any]:
    tl = data.get("timeline", [{}])
    points = tl[0].get("data", []) if tl else []
    values = [int(p.get("value", 0)) for p in points]
    if not values:
        return {"count": 0, "sum": 0, "max": 0, "peak_time": None}
    peak = max(points, key=lambda p: int(p.get("value", 0)))
    return {
        "count": len(values),
        "sum": sum(values),
        "max": max(values),
        "peak_time": peak.get("date"),
    }
