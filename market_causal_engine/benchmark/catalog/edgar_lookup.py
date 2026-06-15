"""Tiered EDGAR lookup for catalog events (event-date first, fiscal fallback)."""

from __future__ import annotations

from datetime import date, timedelta

from market_causal_engine.benchmark.catalog.cik_resolver import candidate_ciks_for_event
from market_causal_engine.benchmark.catalog.fiscal import fiscal_period_date_range
from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.extraction.edgar_fetch import EdgarFiling, fetch_edgar_8k_package


def _expand_range(date_from: str, date_to: str, *, pad_days: int = 21) -> tuple[str, str]:
    lo = date.fromisoformat(date_from) - timedelta(days=pad_days)
    hi = date.fromisoformat(date_to) + timedelta(days=pad_days)
    return lo.isoformat(), hi.isoformat()


def fetch_earnings_8k_for_event(
    event: BenchmarkEvent,
    *,
    window_days: int = 7,
) -> tuple[str, EdgarFiling, dict[str, str | int | None]]:
    """
    Resolve earnings 8-K with layered search:
    1) event_date ±45d (corpus labels are usually near the filing)
    2) fiscal quarter window ±21d padding
    3) event_date ±90d last resort
    """
    cik_candidates = candidate_ciks_for_event(event.ticker, event.event_date)
    attempts: list[tuple[str, dict[str, str | int | None]]] = [
        ("event_date_45d", {"window_days": 45}),
    ]
    fiscal = fiscal_period_date_range(event.fiscal_period)
    if fiscal:
        df, dt = _expand_range(fiscal[0], fiscal[1], pad_days=21)
        attempts.append(("fiscal_padded", {"date_from": df, "date_to": dt, "window_days": window_days}))
    attempts.append(("event_date_90d", {"window_days": 90}))

    errors: list[str] = []
    for cik in cik_candidates:
        for strategy, kwargs in attempts:
            try:
                text, filing = fetch_edgar_8k_package(
                    event.ticker,
                    event.event_date,
                    cik=cik,
                    **kwargs,
                )
                meta = {"fetch_strategy": strategy, "cik": cik, **kwargs}
                return text, filing, meta
            except FileNotFoundError as exc:
                errors.append(f"{cik}/{strategy}: {exc}")
                continue

    raise FileNotFoundError(
        f"No 8-K/6-K for {event.ticker} ({event.event_id}); tried: {'; '.join(errors)}"
    )
