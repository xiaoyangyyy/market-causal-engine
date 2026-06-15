"""Market-adjusted abnormal return on an event window."""

from __future__ import annotations

from typing import Any

from market_causal_engine.counterfactuals.returns import (
    bars_to_close_series,
    cumulative_return,
    daily_simple_returns,
    event_window_dates,
)


def estimate_abnormal_return(
    treated_bars: list[dict[str, Any]],
    market_bars: list[dict[str, Any]],
    event_date: str,
    *,
    event_window: tuple[int, int] = (0, 1),
) -> dict[str, Any]:
    treated_closes = bars_to_close_series(treated_bars)
    market_closes = bars_to_close_series(market_bars)
    treated_rets = daily_simple_returns(treated_closes)
    market_rets = daily_simple_returns(market_closes)

    window_dates = event_window_dates(treated_closes, event_date, window=event_window)
    if not window_dates:
        raise ValueError(f"No trading window for {event_date}")

    observed = cumulative_return(treated_rets, window_dates)
    market_cf = cumulative_return(market_rets, window_dates)
    if observed is None or market_cf is None:
        raise ValueError("Insufficient return data for event window")

    effect = observed - market_cf
    return {
        "method": "abnormal_return",
        "benchmark": "SPY",
        "event_window": list(event_window),
        "event_window_dates": window_dates,
        "observed_return": round(observed, 6),
        "counterfactual_return": round(market_cf, 6),
        "effect": round(effect, 6),
        "pre_fit_rmse": None,
    }
