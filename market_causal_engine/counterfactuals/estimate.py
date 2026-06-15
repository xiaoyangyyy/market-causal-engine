"""Unified counterfactual estimation API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from market_causal_engine.benchmark.labels import fetch_ticker_daily_bars
from market_causal_engine.counterfactuals.abnormal_return import estimate_abnormal_return
from market_causal_engine.counterfactuals.controls import select_controls
from market_causal_engine.counterfactuals.factor_model import (
    default_factors_for_ticker,
    estimate_factor_model,
)
from market_causal_engine.counterfactuals.placebo import compute_placebo_rank, placebo_dates, run_placebo_suite
from market_causal_engine.counterfactuals.returns import bars_to_close_series, pre_estimation_dates
from market_causal_engine.counterfactuals.synthetic_control import estimate_synthetic_control

Method = Literal["abnormal_return", "factor_model", "synthetic_control", "auto"]


def _fetch_bars(symbols: list[str], cache: dict[str, list] | None = None) -> dict[str, list]:
    cache = cache or {}
    out: dict[str, list] = {}
    for sym in symbols:
        sym = sym.upper()
        if sym in cache and cache[sym]:
            out[sym] = cache[sym]
            continue
        try:
            bars = fetch_ticker_daily_bars(sym)
        except Exception:
            try:
                bars = fetch_ticker_daily_bars(sym, refresh=True)
            except Exception:  # noqa: BLE001
                continue
        if bars:
            out[sym] = bars
            cache[sym] = bars
    return out


def _choose_method(method: Method, *, prefer_sc: bool) -> str:
    if method != "auto":
        return method
    return "synthetic_control" if prefer_sc else "abnormal_return"


def estimate_outcome_causal(
    ticker: str,
    event_date: str,
    *,
    method: Method = "auto",
    controls: list[str] | None = None,
    event_window: tuple[int, int] = (0, 1),
    est_days: int = 120,
    run_placebo: bool = True,
    n_placebos: int = 20,
    bars_cache: dict[str, list] | None = None,
    prefer_sc: bool = True,
    include_alternates: bool = True,
) -> dict[str, Any]:
    """
    Estimate market-level causal effect for a ticker event.

    Returns schema aligned with Phase 1 spec (method, treated, controls, effect, …).
    """
    treated = ticker.upper()
    control_list = controls or select_controls(treated)
    chosen = _choose_method(method, prefer_sc=prefer_sc)

    # Always need treated + SPY; SC/factor need full control set + factor ETFs.
    factor_syms = ["SPY", "QQQ"]
    sector = select_controls(treated)  # includes sector etf
    all_syms = sorted({treated, *control_list, *factor_syms, *sector})
    bars = _fetch_bars(all_syms, bars_cache)

    if treated not in bars:
        raise ValueError(f"No price history for treated ticker {treated}")
    if "SPY" not in bars:
        raise ValueError("SPY benchmark bars unavailable")

    primary: dict[str, Any]
    if chosen == "abnormal_return":
        primary = estimate_abnormal_return(
            bars[treated], bars["SPY"], event_date, event_window=event_window
        )
        primary["controls"] = ["SPY"]
    elif chosen == "factor_model":
        factors = default_factors_for_ticker(treated, bars)
        if len(factors) < 2:
            factors = {k: bars[k] for k in ("SPY", "QQQ") if k in bars}
        primary = estimate_factor_model(
            bars[treated], factors, event_date, event_window=event_window, est_days=est_days
        )
        primary["controls"] = list(factors.keys())
    else:
        usable_controls = [c for c in control_list if c in bars and c != treated]
        if len(usable_controls) < 2:
            usable_controls = [c for c in ("SPY", "QQQ") if c in bars and c != treated]
        primary = estimate_synthetic_control(
            bars[treated],
            bars,
            event_date,
            controls=usable_controls,
            event_window=event_window,
            est_days=est_days,
        )

    result: dict[str, Any] = {
        "treated": treated,
        "event_date": event_date,
        "event_window": list(event_window),
        **primary,
    }

    # Compute alternate methods for case-study reports (skip for bulk benchmark).
    alternates: dict[str, Any] = {}
    if include_alternates:
        try:
            alternates["abnormal_return"] = estimate_abnormal_return(
                bars[treated], bars["SPY"], event_date, event_window=event_window
            )
        except Exception as exc:  # noqa: BLE001
            alternates["abnormal_return"] = {"error": str(exc)}

        try:
            factors = default_factors_for_ticker(treated, bars)
            if factors:
                alternates["factor_model"] = estimate_factor_model(
                    bars[treated], factors, event_date, event_window=event_window, est_days=est_days
                )
        except Exception as exc:  # noqa: BLE001
            alternates["factor_model"] = {"error": str(exc)}

        try:
            usable_controls = [c for c in (controls or select_controls(treated)) if c in bars and c != treated]
            if len(usable_controls) >= 2:
                alternates["synthetic_control"] = estimate_synthetic_control(
                    bars[treated],
                    bars,
                    event_date,
                    controls=usable_controls,
                    event_window=event_window,
                    est_days=est_days,
                )
        except Exception as exc:  # noqa: BLE001
            alternates["synthetic_control"] = {"error": str(exc)}

    result["alternates"] = alternates

    if run_placebo and chosen == "synthetic_control":
        treated_closes = bars_to_close_series(bars[treated])
        pre = pre_estimation_dates(treated_closes, event_date, est_days=est_days)
        p_dates = placebo_dates(pre, n_placebos=n_placebos, seed=hash(f"{treated}:{event_date}") % 2**31)
        usable_controls = result.get("controls") or control_list

        def _sc_effect(d: str) -> float:
            out = estimate_synthetic_control(
                bars[treated],
                bars,
                d,
                controls=list(usable_controls),
                event_window=event_window,
                est_days=est_days,
            )
            return float(out["effect"])

        placebo_out = run_placebo_suite(p_dates, _sc_effect)
        result["placebo_rank"] = compute_placebo_rank(float(result["effect"]), placebo_out["placebo_effects"])
        result["placebo_n"] = len(placebo_out["placebo_effects"])
    elif run_placebo and chosen == "abnormal_return":
        treated_closes = bars_to_close_series(bars[treated])
        pre = pre_estimation_dates(treated_closes, event_date, est_days=est_days)
        p_dates = placebo_dates(pre, n_placebos=n_placebos, seed=hash(f"{treated}:{event_date}") % 2**31)

        def _ar_effect(d: str) -> float:
            out = estimate_abnormal_return(bars[treated], bars["SPY"], d, event_window=event_window)
            return float(out["effect"])

        placebo_out = run_placebo_suite(p_dates, _ar_effect)
        result["placebo_rank"] = compute_placebo_rank(float(result["effect"]), placebo_out["placebo_effects"])
        result["placebo_n"] = len(placebo_out["placebo_effects"])
    else:
        result["placebo_rank"] = None

    result["computed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return result
