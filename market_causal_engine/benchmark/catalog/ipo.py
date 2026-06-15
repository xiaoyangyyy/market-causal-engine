"""Detect pre-IPO and other invalid earnings catalog dates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.labels import (
    TICKER_ALIASES,
    compute_earnings_return,
    enrich_event_record,
    fetch_ticker_daily_bars,
)
from market_causal_engine.benchmark.models import BENCHMARK_DIR

DEFAULT_CORPUS = BENCHMARK_DIR / "earnings_sp500_2016_2025.jsonl"
DEFAULT_EXCLUDED = BENCHMARK_DIR / "earnings_sp500_2016_2025_excluded.jsonl"


def first_trading_date(bars: list[dict[str, Any]]) -> str | None:
    if not bars:
        return None
    return min(str(bar["time"])[:10] for bar in bars)


def classify_exclusion(
    record: dict[str, Any],
    *,
    bars: list[dict[str, Any]] | None = None,
    bars_by_ticker: dict[str, list[dict[str, Any]]] | None = None,
) -> str | None:
    """
    Return exclusion reason or None if the event should stay in the main corpus.

    Primary filter: event_date before the ticker's first Yahoo daily bar (IPO proxy).
    """
    ticker = str(record.get("ticker", "")).upper()
    event_date = str(record.get("event_date", ""))
    if not ticker or not event_date:
        return "invalid_record"

    if bars is None:
        if bars_by_ticker is not None:
            bars = bars_by_ticker.get(ticker, [])
        else:
            sym = TICKER_ALIASES.get(ticker, ticker)
            cache_path = BENCHMARK_DIR / "cache" / "ticker_daily_bars.json"
            if cache_path.exists():
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                bars = cache.get(sym, cache.get(ticker, []))
            else:
                bars = []

    first = first_trading_date(bars)
    if first is None:
        meta = record.get("metadata", {})
        if meta.get("label_fetch_error"):
            return "ticker_fetch_error"
        if meta.get("label_fetch_status") == "missing_bar":
            return "no_price_history"
        return None

    if event_date < first:
        return "pre_ipo"

    if compute_earnings_return(bars, event_date) is None:
        return "unpriceable_date"

    return None


def clean_earnings_corpus(
    corpus_path: Path | None = None,
    *,
    excluded_path: Path | None = None,
    re_enrich: bool = True,
    refresh_prices: bool = False,
) -> dict[str, Any]:
    """Move pre-IPO / unpriceable events to excluded JSONL and re-enrich the valid set."""
    src = corpus_path or DEFAULT_CORPUS
    excluded_dest = excluded_path or DEFAULT_EXCLUDED

    lines = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    tickers = sorted({str(r["ticker"]).upper() for r in lines})

    bars_by_ticker: dict[str, list[dict[str, Any]]] = {}
    fetch_errors: dict[str, str] = {}
    for ticker in tickers:
        try:
            bars_by_ticker[ticker] = fetch_ticker_daily_bars(ticker, refresh=refresh_prices)
        except Exception as exc:  # noqa: BLE001
            fetch_errors[ticker] = str(exc)
            bars_by_ticker[ticker] = []

    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}

    for record in lines:
        reason = classify_exclusion(record, bars=bars_by_ticker.get(str(record["ticker"]).upper(), []))
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
            out = dict(record)
            meta = dict(out.get("metadata", {}))
            meta["excluded"] = True
            meta["exclusion_reason"] = reason
            out["metadata"] = meta
            excluded.append(out)
        else:
            valid.append(record)

    if re_enrich:
        enriched_valid: list[dict[str, Any]] = []
        for record in valid:
            ticker = str(record["ticker"]).upper()
            enriched_valid.append(enrich_event_record(record, bars=bars_by_ticker.get(ticker, [])))
        valid = enriched_valid

    src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in valid) + "\n", encoding="utf-8")

    prior_excluded: dict[str, dict[str, Any]] = {}
    if excluded_dest.exists():
        for line in excluded_dest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                prior_excluded[str(rec.get("event_id"))] = rec
    for rec in excluded:
        prior_excluded[str(rec.get("event_id"))] = rec
    merged_excluded = list(prior_excluded.values())
    excluded_dest.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in merged_excluded) + "\n",
        encoding="utf-8",
    )

    real_labels = sum(1 for r in valid if not r.get("metadata", {}).get("synthetic_labels"))
    return {
        "input_total": len(lines),
        "valid": len(valid),
        "excluded": len(merged_excluded),
        "excluded_this_run": len(excluded),
        "exclusion_reasons": reasons,
        "real_labels": real_labels,
        "ticker_fetch_errors": fetch_errors,
        "corpus_path": str(src),
        "excluded_path": str(excluded_dest),
    }
