"""Fetch SEC EDGAR filings (8-K, etc.) into case study source documents."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_causal_engine.extraction.pipeline import _case_root, load_sources_manifest

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "cache" / "edgar"
_MIN_REQUEST_INTERVAL = 0.12
_last_request_at = 0.0


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


def _user_agent() -> str:
    return os.environ.get(
        "MARKET_CAUSAL_SEC_USER_AGENT",
        "MarketCausalEngine/1.0 (research@example.com)",
    )


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


def _cache_path(name: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / name


def resolve_cik(ticker: str, *, refresh: bool = False) -> str:
    """Return zero-padded 10-digit CIK for a ticker."""
    cache = _cache_path("company_tickers.json")
    if refresh or not cache.exists():
        raw = _http_get("https://www.sec.gov/files/company_tickers.json")
        cache.write_bytes(raw)
    data = json.loads(cache.read_text(encoding="utf-8"))
    upper = ticker.upper()
    for entry in data.values():
        if str(entry.get("ticker", "")).upper() == upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker not found in SEC company_tickers: {ticker}")


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


@dataclass(frozen=True)
class EdgarFiling:
    form: str
    filing_date: str
    accession_number: str
    primary_document: str
    cik: str

    @property
    def cik_int(self) -> str:
        return str(int(self.cik))

    @property
    def accession_no_dashes(self) -> str:
        return self.accession_number.replace("-", "")

    def document_url(self) -> str:
        return (
            f"https://www.sec.gov/Archives/edgar/data/{self.cik_int}/"
            f"{self.accession_no_dashes}/{self.primary_document}"
        )


def _parse_event_date(event_date: str) -> tuple[int, int, int]:
    year, month, day = (int(x) for x in event_date.split("-"))
    return year, month, day


def _date_in_window(filing_date: str, event_date: str, window_days: int) -> bool:
    fy, fm, fd = _parse_event_date(filing_date)
    ey, em, ed = _parse_event_date(event_date)
    filing_ord = fy * 372 + fm * 31 + fd
    event_ord = ey * 372 + em * 31 + ed
    return abs(filing_ord - event_ord) <= window_days


def find_filings(
    cik: str,
    *,
    forms: tuple[str, ...] = ("8-K",),
    event_date: str,
    window_days: int = 2,
) -> list[EdgarFiling]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    payload = json.loads(_http_get(url).decode("utf-8"))
    recent = payload.get("filings", {}).get("recent", {})
    forms_list = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])

    hits: list[EdgarFiling] = []
    for form, fdate, acc, primary in zip(forms_list, dates, accessions, primaries, strict=False):
        if form not in forms:
            continue
        if not _date_in_window(fdate, event_date, window_days):
            continue
        hits.append(
            EdgarFiling(
                form=form,
                filing_date=fdate,
                accession_number=acc,
                primary_document=primary,
                cik=cik,
            )
        )
    return hits


def fetch_filing_text(filing: EdgarFiling) -> str:
    raw = _http_get(filing.document_url())
    text = raw.decode("utf-8", errors="replace")
    if "<html" in text.lower() or "<body" in text.lower():
        text = html_to_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_edgar_8k(
    ticker: str,
    event_date: str,
    *,
    window_days: int = 2,
    prefer_item: str | None = "2.02",
) -> tuple[str, EdgarFiling]:
    """Fetch the best-matching 8-K plain text for ticker near event_date."""
    cik = resolve_cik(ticker)
    filings = find_filings(cik, forms=("8-K",), event_date=event_date, window_days=window_days)
    if not filings:
        raise FileNotFoundError(
            f"No 8-K found for {ticker} within ±{window_days}d of {event_date}"
        )

    best: tuple[str, EdgarFiling] | None = None
    for filing in filings:
        text = fetch_filing_text(filing)
        if prefer_item and prefer_item.replace(".", "") in text.replace(" ", ""):
            return text, filing
        if best is None or len(text) > len(best[0]):
            best = (text, filing)
    assert best is not None
    return best


def fetch_edgar_for_case(case_id: str, *, overwrite: bool = True) -> dict[str, Any]:
    """
    Read sources.json `edgar` block, download filing(s), write into sources/.
    """
    root = _case_root(case_id)
    manifest = load_sources_manifest(case_id)
    edgar_cfg = manifest.get("edgar")
    if not edgar_cfg:
        raise ValueError(f"Case {case_id} sources.json has no 'edgar' configuration")

    ticker = edgar_cfg["ticker"]
    event_date = edgar_cfg.get("event_date") or manifest.get("origin", {}).get("timestamp_et", "")[:10]
    if not event_date:
        case_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        event_date = case_manifest.get("event_date")
    if not event_date:
        raise ValueError(f"Cannot determine event_date for EDGAR fetch: {case_id}")

    window_days = int(edgar_cfg.get("window_days", 2))
    output_name = edgar_cfg.get("output", "sec_8k_edgar.txt")
    out_path = root / "sources" / output_name

    text, filing = fetch_edgar_8k(ticker, event_date, window_days=window_days)
    if len(text) > 120_000:
        text = text[:120_000] + "\n\n[truncated for case study pipeline]"

    from market_causal_engine.extraction.edgar_preprocess import preprocess_edgar_filing

    summary_name = edgar_cfg.get("summary_output", "sec_8k_edgar_summary.txt")
    summary_path = root / "sources" / summary_name
    summary_text = preprocess_edgar_filing(text)

    if overwrite or not out_path.exists():
        out_path.write_text(text, encoding="utf-8")
    if overwrite or not summary_path.exists():
        summary_path.write_text(summary_text, encoding="utf-8")

    meta_path = root / "sources" / "edgar_fetch.json"
    report = {
        "case_id": case_id,
        "ticker": ticker,
        "event_date": event_date,
        "filing_date": filing.filing_date,
        "accession_number": filing.accession_number,
        "document_url": filing.document_url(),
        "output_path": str(out_path),
        "summary_path": str(summary_path),
        "summary_length": len(summary_text),
        "text_length": len(text),
    }
    meta_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def list_edgar_fetchable_cases() -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies"
    cases: list[str] = []
    for case_dir in sorted(root.iterdir()):
        sources = case_dir / "sources" / "sources.json"
        if not sources.exists():
            continue
        data = json.loads(sources.read_text(encoding="utf-8"))
        if data.get("edgar"):
            cases.append(case_dir.name)
    return cases


def fetch_all_edgar_cases(*, overwrite: bool = True) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case_id in list_edgar_fetchable_cases():
        try:
            results.append(fetch_edgar_for_case(case_id, overwrite=overwrite))
        except (HTTPError, URLError, ValueError, FileNotFoundError) as exc:
            results.append({"case_id": case_id, "error": str(exc)})
    return results
