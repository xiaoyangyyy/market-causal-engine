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

EARNINGS_FILING_FORMS = ("8-K", "6-K")

_ATTACHMENT_POSITIVE = (
    (re.compile(r"financial", re.I), 16),
    (re.compile(r"press.?release|earnings.?release", re.I), 15),
    (re.compile(r"shareholder|investor.?letter|results.?release", re.I), 14),
    (re.compile(r"\bmda\b|management.?s.?discussion", re.I), 13),
    (re.compile(r"ex99|ex-99|exhibit.?99", re.I), 10),
    (re.compile(r"earnings|quarterly.?report", re.I), 9),
)
_ATTACHMENT_NEGATIVE = (
    re.compile(r"109f|certification|certify|52-109", re.I),
    re.compile(r"cover.?page|graphic|\.jpg|\.png|\.gif|\.xml|\.xsd", re.I),
    re.compile(r"index\.(html|htm|json|headers)", re.I),
)


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
    from market_causal_engine.benchmark.labels import TICKER_ALIASES

    ticker = TICKER_ALIASES.get(ticker.upper(), ticker)
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


def _event_window_ordinals(event_date: str, window_days: int) -> tuple[int, int]:
    ey, em, ed = _parse_event_date(event_date)
    center = ey * 372 + em * 31 + ed
    return center - window_days, center + window_days


def _date_in_window(filing_date: str, event_date: str, window_days: int) -> bool:
    fy, fm, fd = _parse_event_date(filing_date)
    filing_ord = fy * 372 + fm * 31 + fd
    lo, hi = _event_window_ordinals(event_date, window_days)
    return lo <= filing_ord <= hi


def _batch_covers_event(entry: dict[str, Any], event_date: str, window_days: int) -> bool:
    if entry.get("name") == "recent" or "data" in entry:
        return True
    filing_from = str(entry.get("filingFrom", ""))
    filing_to = str(entry.get("filingTo", ""))
    if not filing_from or not filing_to:
        return True
    lo, hi = _event_window_ordinals(event_date, window_days)
    from_ord = _parse_event_date(filing_from)
    to_ord = _parse_event_date(filing_to)
    from_val = from_ord[0] * 372 + from_ord[1] * 31 + from_ord[2]
    to_val = to_ord[0] * 372 + to_ord[1] * 31 + to_ord[2]
    return not (to_val < lo or from_val > hi)


def _scan_submission_batch(
    batch: dict[str, Any],
    *,
    cik: str,
    forms: tuple[str, ...],
    event_date: str,
    window_days: int,
) -> list[EdgarFiling]:
    forms_list = batch.get("form", [])
    dates = batch.get("filingDate", [])
    accessions = batch.get("accessionNumber", [])
    primaries = batch.get("primaryDocument", [])

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


def _submission_entries(cik: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    filings = payload.get("filings", {})
    entries: list[dict[str, Any]] = [{"name": "recent", "data": filings.get("recent", {})}]
    for entry in filings.get("files", []):
        entries.append(dict(entry))
    return entries


def _load_submission_batch(cik: str, entry: dict[str, Any]) -> dict[str, Any]:
    if "data" in entry:
        return entry["data"]
    name = str(entry["name"])
    url = f"https://data.sec.gov/submissions/{name}"
    return json.loads(_http_get(url).decode("utf-8"))


def find_filings_in_range(
    cik: str,
    *,
    forms: tuple[str, ...] = ("8-K",),
    date_from: str,
    date_to: str,
) -> list[EdgarFiling]:
    """Return filings with filingDate in [date_from, date_to] (inclusive)."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    payload = json.loads(_http_get(url).decode("utf-8"))

    lo = _parse_event_date(date_from)
    hi = _parse_event_date(date_to)
    lo_ord = lo[0] * 372 + lo[1] * 31 + lo[2]
    hi_ord = hi[0] * 372 + hi[1] * 31 + hi[2]

    hits: list[EdgarFiling] = []
    seen: set[str] = set()
    for entry in _submission_entries(cik, payload):
        filing_from = str(entry.get("filingFrom", date_from))
        filing_to = str(entry.get("filingTo", date_to))
        if entry.get("name") != "recent" and "data" not in entry:
            from_ord = _parse_event_date(filing_from)
            to_ord = _parse_event_date(filing_to)
            batch_lo = from_ord[0] * 372 + from_ord[1] * 31 + from_ord[2]
            batch_hi = to_ord[0] * 372 + to_ord[1] * 31 + to_ord[2]
            if batch_hi < lo_ord or batch_lo > hi_ord:
                continue
        batch = _load_submission_batch(cik, entry)
        forms_list = batch.get("form", [])
        dates = batch.get("filingDate", [])
        accessions = batch.get("accessionNumber", [])
        primaries = batch.get("primaryDocument", [])

        for form, fdate, acc, primary in zip(forms_list, dates, accessions, primaries, strict=False):
            if form not in forms:
                continue
            fy, fm, fd = _parse_event_date(fdate)
            filing_ord = fy * 372 + fm * 31 + fd
            if filing_ord < lo_ord or filing_ord > hi_ord:
                continue
            if acc in seen:
                continue
            seen.add(acc)
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


def _scan_submission_batch_in_range(
    batch: dict[str, Any],
    *,
    cik: str,
    forms: tuple[str, ...],
    date_from: str,
    date_to: str,
) -> list[EdgarFiling]:
    forms_list = batch.get("form", [])
    dates = batch.get("filingDate", [])
    accessions = batch.get("accessionNumber", [])
    primaries = batch.get("primaryDocument", [])

    hits: list[EdgarFiling] = []
    for form, fdate, acc, primary in zip(forms_list, dates, accessions, primaries, strict=False):
        if form not in forms:
            continue
        if not (date_from <= fdate <= date_to):
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


def find_filings(
    cik: str,
    *,
    forms: tuple[str, ...] = ("8-K",),
    event_date: str,
    window_days: int = 2,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[EdgarFiling]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    payload = json.loads(_http_get(url).decode("utf-8"))

    hits: list[EdgarFiling] = []
    seen: set[str] = set()
    for entry in _submission_entries(cik, payload):
        if date_from and date_to:
            if not _batch_covers_event(entry, date_from, 120) and not _batch_covers_event(
                entry, date_to, 120
            ):
                continue
            batch = _load_submission_batch(cik, entry)
            batch_hits = _scan_submission_batch_in_range(
                batch,
                cik=cik,
                forms=forms,
                date_from=date_from,
                date_to=date_to,
            )
        else:
            if not _batch_covers_event(entry, event_date, window_days):
                continue
            batch = _load_submission_batch(cik, entry)
            batch_hits = _scan_submission_batch(
                batch,
                cik=cik,
                forms=forms,
                event_date=event_date,
                window_days=window_days,
            )
        for filing in batch_hits:
            if filing.accession_number in seen:
                continue
            seen.add(filing.accession_number)
            hits.append(filing)
    return hits


def fetch_filing_text(filing: EdgarFiling) -> str:
    raw = _http_get(filing.document_url())
    text = raw.decode("utf-8", errors="replace")
    if "<html" in text.lower() or "<body" in text.lower():
        text = html_to_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_filing_index(filing: EdgarFiling) -> list[dict[str, Any]]:
    """Return directory listing entries for a filing accession."""
    base = (
        f"https://www.sec.gov/Archives/edgar/data/{filing.cik_int}/"
        f"{filing.accession_no_dashes}/"
    )
    for suffix in ("index.json", f"{filing.accession_number}-index.json"):
        index_url = base + suffix
        try:
            payload = json.loads(_http_get(index_url).decode("utf-8"))
            return list(payload.get("directory", {}).get("item", []))
        except (HTTPError, URLError, json.JSONDecodeError, KeyError):
            continue
    return []


def _score_attachment(name: str, description: str = "") -> int:
    label = f"{name} {description}".lower()
    if any(p.search(label) for p in _ATTACHMENT_NEGATIVE):
        return -1
    score = 0
    for pattern, weight in _ATTACHMENT_POSITIVE:
        if pattern.search(label):
            score += weight
    if label.endswith((".htm", ".html", ".txt")):
        score += 1
    return score


def fetch_attachment_text(filing: EdgarFiling, filename: str) -> str:
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{filing.cik_int}/"
        f"{filing.accession_no_dashes}/{filename}"
    )
    raw = _http_get(url).decode("utf-8", errors="replace")
    if "<html" in raw.lower() or "<body" in raw.lower():
        raw = html_to_text(raw)
    return re.sub(r"\s+", " ", raw).strip()


def fetch_earnings_attachments(
    filing: EdgarFiling,
    *,
    max_documents: int = 4,
) -> str:
    """
    Fetch the best earnings-related attachments for a filing package.

    Handles Exhibit 99.x press releases (8-K) and foreign-issuer financials/MDA (6-K).
    """
    try:
        items = fetch_filing_index(filing)
    except (HTTPError, URLError, json.JSONDecodeError, KeyError):
        items = []

    candidates: list[tuple[int, str]] = []
    for item in items:
        name = str(item.get("name", ""))
        desc = str(item.get("description", ""))
        if name.lower() == filing.primary_document.lower():
            continue
        score = _score_attachment(name, desc)
        if score > 0:
            candidates.append((score, name))

    candidates.sort(key=lambda x: x[0], reverse=True)
    parts: list[str] = []
    for _score, name in candidates[:max_documents]:
        try:
            text = fetch_attachment_text(filing, name)
        except (HTTPError, URLError, TimeoutError):
            continue
        if len(text) >= 120:
            parts.append(text)

    return "\n\n".join(parts)


def fetch_exhibit_text(filing: EdgarFiling, exhibit_name: str = "99.1") -> str | None:
    """Fetch exhibit document text (e.g. 99.1 shareholder letter) when present."""
    attachments = fetch_earnings_attachments(filing, max_documents=3)
    if attachments:
        return attachments
    try:
        items = fetch_filing_index(filing)
    except (HTTPError, URLError, json.JSONDecodeError, KeyError):
        return None

    target: str | None = None
    best_score = -1
    for item in items:
        name = str(item.get("name", ""))
        desc = str(item.get("description", ""))
        score = _score_attachment(name, desc)
        if exhibit_name.replace(".", "") in name.replace(".", "").replace("-", ""):
            score += 5
        if score > best_score:
            best_score = score
            target = name

    if not target or best_score <= 0:
        return None

    try:
        return fetch_attachment_text(filing, target)
    except (HTTPError, URLError, TimeoutError):
        return None


def _score_earnings_package(body: str, attachments: str | None) -> float:
    combined = f"{body}\n{attachments or ''}".lower()
    score = 0.0
    for kw in ("revenue", "earnings", "eps", "guidance", "subscriber", "net income", "quarter"):
        if kw in combined:
            score += 1.0
    if attachments:
        score += min(len(attachments) / 1200.0, 8.0)
    if "2.02" in body.replace(" ", "") or "item202" in body.lower().replace(" ", ""):
        score += 4.0
    if "results of operations" in combined or "financial results" in combined:
        score += 3.0
    if "form 6-k" in body.lower() and attachments:
        score += 2.0
    # Penalize non-earnings 8-K filings (proxy votes, officer changes, etc.)
    for penalty_kw in (
        "item 5.02",
        "item 5.07",
        "item 8.01",
        "departure of directors",
        "appointment of certain officers",
        "submission of matters to a vote",
        "annual meeting of stockholders",
        "special meeting of stockholders",
        "change in shell company",
    ):
        if penalty_kw in combined:
            score -= 3.0
    return score


def fetch_edgar_8k_package(
    ticker: str,
    event_date: str,
    *,
    window_days: int = 2,
    date_from: str | None = None,
    date_to: str | None = None,
    forms: tuple[str, ...] = EARNINGS_FILING_FORMS,
    cik: str | None = None,
) -> tuple[str, EdgarFiling]:
    """Fetch 8-K/6-K body plus earnings attachments (Exhibit 99.x, financials, MD&A)."""
    resolved_cik = cik or resolve_cik(ticker)
    filings = find_filings(
        resolved_cik,
        forms=forms,
        event_date=event_date,
        window_days=window_days,
        date_from=date_from,
        date_to=date_to,
    )
    if not filings:
        form_label = "/".join(forms)
        if date_from and date_to:
            raise FileNotFoundError(
                f"No {form_label} found for {ticker} between {date_from} and {date_to}"
            )
        raise FileNotFoundError(
            f"No {form_label} found for {ticker} within ±{window_days}d of {event_date}"
        )

    best: tuple[str, EdgarFiling, float] | None = None
    for filing in filings:
        body = fetch_filing_text(filing)
        attachments = fetch_earnings_attachments(filing)
        text = body
        if attachments:
            text = f"{body}\n\n{attachments}"
        score = _score_earnings_package(body, attachments)
        if best is None or score > best[2]:
            best = (text, filing, score)

    assert best is not None
    return best[0], best[1]


def fetch_edgar_8k(
    ticker: str,
    event_date: str,
    *,
    window_days: int = 2,
    prefer_item: str | None = "2.02",
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, EdgarFiling]:
    """Fetch the best-matching 8-K plain text for ticker near event_date."""
    cik = resolve_cik(ticker)
    filings = find_filings(
        cik,
        forms=("8-K",),
        event_date=event_date,
        window_days=window_days,
        date_from=date_from,
        date_to=date_to,
    )
    if not filings:
        if date_from and date_to:
            raise FileNotFoundError(
                f"No 8-K found for {ticker} between {date_from} and {date_to}"
            )
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


def list_recent_filings(
    ticker: str,
    *,
    lookback_days: int = 30,
    forms: tuple[str, ...] = ("8-K",),
) -> list[EdgarFiling]:
    """Return filings for ticker within the last lookback_days (calendar)."""
    from datetime import date, timedelta

    cik = resolve_cik(ticker)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    payload = json.loads(_http_get(url).decode("utf-8"))
    recent = payload.get("filings", {}).get("recent", {})
    forms_list = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primaries = recent.get("primaryDocument", [])

    cutoff = date.today() - timedelta(days=lookback_days)
    hits: list[EdgarFiling] = []
    for form, fdate, acc, primary in zip(forms_list, dates, accessions, primaries, strict=False):
        if form not in forms:
            continue
        try:
            fy, fm, fd = (int(x) for x in fdate.split("-"))
            if date(fy, fm, fd) < cutoff:
                continue
        except ValueError:
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
