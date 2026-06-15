"""Fetch real market labels for benchmark events (Yahoo daily bars)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.platform.ingestion.market_prices import _parse_bars, _yahoo_chart

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "cache"
TICKER_BARS_CACHE = CACHE_DIR / "ticker_daily_bars.json"
STATIC_BARS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "market" / "counterfactuals" / "static_bars"
)

TICKER_ALIASES = {
    "BRK.B": "BRK-B",
    "BRK.A": "BRK-A",
    "LK": "LKNCY",
}


def _direction_from_return(ret_pct: float, *, neutral_band: float = 1.0) -> str:
    if ret_pct > neutral_band:
        return "up"
    if ret_pct < -neutral_band:
        return "down"
    return "neutral"


def _magnitude_bucket(ret_pct: float) -> str:
    a = abs(ret_pct)
    if a >= 8.0:
        return "large"
    if a >= 3.0:
        return "medium"
    if a >= 1.0:
        return "small"
    return "none"


def _scenario_from_direction(direction: str) -> str:
    return "E2" if direction == "up" else "E1"


def _load_ticker_cache() -> dict[str, list[dict[str, Any]]]:
    if not TICKER_BARS_CACHE.exists():
        return {}
    return json.loads(TICKER_BARS_CACHE.read_text(encoding="utf-8"))


def _save_ticker_cache(cache: dict[str, list[dict[str, Any]]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TICKER_BARS_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _load_static_bars(sym: str) -> list[dict[str, Any]] | None:
    path = STATIC_BARS_DIR / f"{sym}.json"
    if not path.exists():
        return None
    bars = json.loads(path.read_text(encoding="utf-8"))
    return bars if bars else None


def fetch_ticker_daily_bars(ticker: str, *, refresh: bool = False, max_attempts: int = 3) -> list[dict[str, Any]]:
    cache = _load_ticker_cache()
    sym = TICKER_ALIASES.get(ticker.upper(), ticker.upper())
    if not refresh and sym in cache and cache[sym]:
        return cache[sym]

    static = _load_static_bars(sym)
    if static and not refresh:
        cache[sym] = static
        _save_ticker_cache(cache)
        return static

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            payload = _yahoo_chart(sym, interval="1d", range_="10y")
            bars = _parse_bars(payload)
            if bars:
                cache[sym] = bars
                _save_ticker_cache(cache)
                time.sleep(0.15)
                return bars
            last_exc = ValueError(f"Empty Yahoo response for {sym}")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        if attempt + 1 < max_attempts:
            time.sleep(0.35 * (2**attempt))

    if static:
        cache[sym] = static
        _save_ticker_cache(cache)
        return static

    raise ValueError(f"No price history for {sym} (Yahoo unavailable, no static bars)") from last_exc


def _bar_by_date(bars: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for bar in bars:
        out[bar["time"][:10]] = bar
    return out


def compute_earnings_return(
    bars: list[dict[str, Any]],
    event_date: str,
) -> dict[str, Any] | None:
    """
    Overnight + first session proxy for after-close earnings:
    (close[event_date] - close[prev]) / close[prev] * 100
    Falls back to (open[event] - prev_close) when close missing.
    """
    if not bars:
        return None

    by_date = _bar_by_date(bars)
    if event_date not in by_date:
        return None

    try:
        dt = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None

    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    # walk back up to 5 days for prev trading day
    prev_bar = None
    for i in range(1, 8):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in by_date:
            prev_bar = by_date[d]
            break
    if prev_bar is None:
        return None

    event_bar = by_date[event_date]
    prev_close = float(prev_bar["close"])
    if prev_close <= 0:
        return None

    event_close = float(event_bar.get("close") or event_bar.get("open") or 0)
    if event_close <= 0:
        return None

    ret_pct = round((event_close - prev_close) / prev_close * 100.0, 2)
    direction = _direction_from_return(ret_pct)
    return {
        "after_hours_return_pct": ret_pct,
        "direction": direction,
        "magnitude_bucket": _magnitude_bucket(ret_pct),
        "label_method": "yahoo_daily_close_vs_prev_close",
        "prev_close": prev_close,
        "event_close": event_close,
        "event_date": event_date,
    }


def enrich_event_record(record: dict[str, Any], bars: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return updated benchmark JSONL record with real labels."""
    ticker = str(record.get("ticker", "")).upper()
    event_date = str(record.get("event_date", ""))
    if bars is None:
        try:
            bars = fetch_ticker_daily_bars(ticker)
        except Exception as exc:  # noqa: BLE001
            record.setdefault("metadata", {})
            record["metadata"]["label_fetch_error"] = str(exc)
            return record

    label = compute_earnings_return(bars, event_date)
    out = dict(record)
    meta = dict(out.get("metadata", {}))

    if label is None:
        meta["label_source"] = "yahoo_daily"
        meta["label_fetch_status"] = "missing_bar"
        meta["synthetic_labels"] = True
        out["metadata"] = meta
        return out

    direction = label["direction"]
    ret = label["after_hours_return_pct"]
    out["observed_outcomes"] = {
        "direction": direction,
        "after_hours_return_pct": ret,
        "magnitude_bucket": label["magnitude_bucket"],
        "calibration_reference_drawdown": 0.72 if direction == "down" else None,
    }
    out["scenario_id"] = _scenario_from_direction(direction)
    out["labels"] = {
        "is_major_event": abs(ret) >= 3.0,
        "is_placebo": False,
    }
    meta.update(
        {
            "label_source": "yahoo_daily",
            "label_method": label["label_method"],
            "synthetic_labels": False,
            "label_fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    )
    meta.pop("label_fetch_error", None)
    meta.pop("label_fetch_status", None)
    out["metadata"] = meta
    return out


def enrich_earnings_corpus(
    corpus_path: Path,
    *,
    refresh_prices: bool = False,
    write_path: Path | None = None,
) -> dict[str, Any]:
    """Enrich all records in earnings JSONL with Yahoo daily returns."""
    lines = [json.loads(l) for l in corpus_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    tickers = sorted({str(r["ticker"]).upper() for r in lines})

    bars_by_ticker: dict[str, list[dict[str, Any]]] = {}
    fetch_errors: dict[str, str] = {}
    for ticker in tickers:
        try:
            bars_by_ticker[ticker] = fetch_ticker_daily_bars(ticker, refresh=refresh_prices)
        except Exception as exc:  # noqa: BLE001
            fetch_errors[ticker] = str(exc)
            bars_by_ticker[ticker] = []

    enriched: list[dict[str, Any]] = []
    stats = {"total": len(lines), "real_labels": 0, "missing": 0, "errors": 0}

    for record in lines:
        ticker = str(record["ticker"]).upper()
        bars = bars_by_ticker.get(ticker, [])
        new_rec = enrich_event_record(record, bars=bars)
        if new_rec.get("metadata", {}).get("synthetic_labels"):
            if new_rec.get("metadata", {}).get("label_fetch_status") == "missing_bar":
                stats["missing"] += 1
            else:
                stats["errors"] += 1
        else:
            stats["real_labels"] += 1
        enriched.append(new_rec)

    dest = write_path or corpus_path
    dest.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in enriched) + "\n", encoding="utf-8")
    stats["tickers"] = len(tickers)
    stats["ticker_fetch_errors"] = fetch_errors
    stats["output"] = str(dest)
    return stats
