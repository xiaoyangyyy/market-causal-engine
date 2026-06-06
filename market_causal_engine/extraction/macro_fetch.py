"""Fetch FOMC statements and BLS CPI releases into case study sources."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_causal_engine.extraction.edgar_fetch import _user_agent, html_to_text
from market_causal_engine.extraction.pipeline import _case_root, load_sources_manifest

_MIN_REQUEST_INTERVAL = 0.12
_last_request_at = 0.0


def _http_get(url: str, *, timeout: float = 30.0, retries: int = 3) -> bytes:
    global _last_request_at
    last_error: Exception | None = None
    for attempt in range(retries):
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        req = Request(url, headers={"User-Agent": _user_agent(), "Accept-Encoding": "identity"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                _last_request_at = time.monotonic()
                return resp.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _normalize_date(date: str) -> str:
    return date.replace("-", "")


def _fomc_urls(event_date: str) -> list[str]:
    ymd = _normalize_date(event_date)
    return [
        f"https://www.federalreserve.gov/monetarypolicy/fomcstatement{ymd}.htm",
        f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{ymd}a.htm",
    ]


def fetch_fomc_statement(event_date: str) -> str:
    """Download FOMC statement prose for a meeting date (YYYY-MM-DD)."""
    errors: list[str] = []
    for url in _fomc_urls(event_date):
        try:
            raw = _http_get(url).decode("utf-8", errors="replace")
            text = html_to_text(raw)
            lower = text.lower()
            if len(text) >= 120 and any(k in lower for k in ("fomc", "federal reserve", "interest rate")):
                return text[:120_000]
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")
    raise FileNotFoundError(f"No FOMC statement found for {event_date}. Tried: {errors}")


def _cpi_archive_urls(release_date: str) -> list[str]:
    parts = release_date.split("-")
    year, month, day = parts[0], parts[1], parts[2]
    mmddyy = f"{month}{day}{year[2:]}"
    return [
        f"https://www.bls.gov/news.release/archives/cpi_{mmddyy}.htm",
        f"https://www.bls.gov/news.release/cpi.nr0.htm",
    ]


def fetch_bls_cpi(release_date: str, *, period_label: str | None = None) -> str:
    """Download BLS CPI release text. release_date is publication date YYYY-MM-DD."""
    errors: list[str] = []
    for url in _cpi_archive_urls(release_date):
        try:
            raw = _http_get(url).decode("utf-8", errors="replace")
            text = html_to_text(raw)
            if len(text) >= 120 and "consumer price index" in text.lower():
                return text[:120_000]
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")
    raise FileNotFoundError(f"No BLS CPI release found for {release_date}. Tried: {errors}")


def list_macro_fetchable_cases() -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies"
    cases: list[str] = []
    for case_dir in sorted(root.iterdir()):
        sources = case_dir / "sources" / "sources.json"
        if not sources.exists():
            continue
        data = json.loads(sources.read_text(encoding="utf-8"))
        if data.get("macro_fetch"):
            cases.append(case_dir.name)
    return cases


def fetch_macro_for_case(case_id: str, *, overwrite: bool = True) -> dict[str, Any]:
    root = _case_root(case_id)
    manifest = load_sources_manifest(case_id)
    cfg = manifest.get("macro_fetch")
    if not cfg:
        raise ValueError(f"Case {case_id} sources.json has no 'macro_fetch' configuration")

    source = cfg.get("source", "fomc")
    output_name = cfg.get("output", "macro_release.txt")
    out_path = root / "sources" / output_name

    if source == "fomc":
        event_date = cfg.get("event_date")
        if not event_date:
            case_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            event_date = case_manifest.get("event_date")
        if not event_date:
            raise ValueError(f"Cannot determine event_date for FOMC fetch: {case_id}")
        text = fetch_fomc_statement(event_date)
        meta: dict[str, Any] = {"source": "fomc", "event_date": event_date}
    elif source == "bls_cpi":
        release_date = cfg.get("release_date")
        if not release_date:
            case_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            release_date = case_manifest.get("event_date")
        if not release_date:
            raise ValueError(f"Cannot determine release_date for CPI fetch: {case_id}")
        text = fetch_bls_cpi(release_date, period_label=cfg.get("period"))
        meta = {"source": "bls_cpi", "release_date": release_date, "period": cfg.get("period")}
    else:
        raise ValueError(f"Unknown macro_fetch source: {source}")

    if overwrite or not out_path.exists():
        out_path.write_text(text, encoding="utf-8")

    meta_path = root / "sources" / "macro_fetch.json"
    report = {
        "case_id": case_id,
        "output_path": str(out_path),
        "text_length": len(text),
        **meta,
    }
    meta_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def fetch_all_macro_cases(*, overwrite: bool = True) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case_id in list_macro_fetchable_cases():
        try:
            results.append(fetch_macro_for_case(case_id, overwrite=overwrite))
        except (HTTPError, URLError, ValueError, FileNotFoundError) as exc:
            results.append({"case_id": case_id, "error": str(exc)})
    return results
