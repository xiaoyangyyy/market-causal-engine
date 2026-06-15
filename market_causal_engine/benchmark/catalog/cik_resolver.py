"""Resolve SEC CIK for benchmark tickers, including historical renames and spin-offs."""

from __future__ import annotations

from market_causal_engine.benchmark.labels import TICKER_ALIASES
from market_causal_engine.extraction.edgar_fetch import resolve_cik as _resolve_cik_current


# (last_event_date_inclusive, cik) — pick first entry where event_date <= cutoff
HISTORICAL_CIK: dict[str, list[tuple[str, str]]] = {
    # Asset-manager earnings through early 2024 still on 1364742; ticker BLK remapped later.
    "BLK": [("2024-06-30", "0001364742"), ("9999-12-31", "0002012383")],
    # Broadcom Inc CIK 1730168 has no pre-2018 history; use Broadcom Pte / Avago era.
    "AVGO": [("2017-12-31", "0001649338"), ("9999-12-31", "0001730168")],
    # Walt Disney Co re-registered under 1744489 in 2018; pre-2018 filings are on 1001039.
    "DIS": [("2018-06-24", "0001001039"), ("9999-12-31", "0001744489")],
}


def normalize_ticker(ticker: str) -> str:
    return TICKER_ALIASES.get(ticker.upper(), ticker.upper())


def resolve_cik_for_event(ticker: str, event_date: str) -> str:
    """Return CIK for ticker at event_date, using historical tables when needed."""
    sym = normalize_ticker(ticker)
    hist = HISTORICAL_CIK.get(sym)
    if hist:
        for cutoff, cik in hist:
            if event_date <= cutoff:
                return cik.zfill(10)
    return _resolve_cik_current(sym)


def candidate_ciks_for_event(ticker: str, event_date: str) -> list[str]:
    """Ordered CIK candidates to try when fetching EDGAR (primary first, then alternates)."""
    sym = normalize_ticker(ticker)
    seen: set[str] = set()
    candidates: list[str] = []

    def add(cik: str) -> None:
        normalized = cik.zfill(10)
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)

    add(resolve_cik_for_event(ticker, event_date))
    hist = HISTORICAL_CIK.get(sym)
    if hist:
        for _, cik in hist:
            add(cik)
    try:
        add(_resolve_cik_current(sym))
    except ValueError:
        pass
    return candidates
