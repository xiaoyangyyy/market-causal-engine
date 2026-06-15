"""Multi-factor OLS counterfactual (market + sector ETF + growth)."""

from __future__ import annotations

from typing import Any

from market_causal_engine.counterfactuals.controls import sector_etf_for
from market_causal_engine.counterfactuals.returns import (
    bars_to_close_series,
    cumulative_return,
    daily_simple_returns,
    event_window_dates,
    ols_fit,
    pre_estimation_dates,
    rmse,
)


def estimate_factor_model(
    treated_bars: list[dict[str, Any]],
    factor_bars: dict[str, list[dict[str, Any]]],
    event_date: str,
    *,
    event_window: tuple[int, int] = (0, 1),
    est_days: int = 120,
) -> dict[str, Any]:
    treated_closes = bars_to_close_series(treated_bars)
    treated_rets = daily_simple_returns(treated_closes)
    factor_rets: dict[str, dict[str, float]] = {}
    for name, bars in factor_bars.items():
        factor_rets[name] = daily_simple_returns(bars_to_close_series(bars))

    pre_dates = pre_estimation_dates(treated_closes, event_date, est_days=est_days)
    factor_names = sorted(factor_rets)
    y = [treated_rets[d] for d in pre_dates if d in treated_rets]
    common_pre = [d for d in pre_dates if d in treated_rets and all(d in factor_rets[f] for f in factor_names)]
    if len(common_pre) < 30:
        raise ValueError(f"Insufficient pre-period overlap ({len(common_pre)} days)")

    y = [treated_rets[d] for d in common_pre]
    x_cols = [[factor_rets[f][d] for d in common_pre] for f in factor_names]
    beta = ols_fit(x_cols, y)
    if beta is None:
        raise ValueError("Factor model OLS failed")

    fitted = [beta[0] + sum(beta[i + 1] * x_cols[i][j] for i in range(len(factor_names))) for j in range(len(common_pre))]
    pre_fit_rmse = rmse(y, fitted)

    window_dates = event_window_dates(treated_closes, event_date, window=event_window)
    observed = cumulative_return(treated_rets, window_dates)
    if observed is None:
        raise ValueError("Missing treated returns on event window")

    # Predict daily treated returns on event window from factor returns, compound.
    acc = 1.0
    for d in window_dates:
        if any(d not in factor_rets[f] for f in factor_names):
            raise ValueError(f"Missing factor returns on {d}")
        pred_daily = beta[0] + sum(beta[i + 1] * factor_rets[factor_names[i]][d] for i in range(len(factor_names)))
        acc *= 1.0 + pred_daily
    counterfactual = acc - 1.0
    effect = observed - counterfactual

    loadings = {"alpha": round(beta[0], 6)}
    for i, name in enumerate(factor_names):
        loadings[name] = round(beta[i + 1], 6)

    return {
        "method": "factor_model",
        "factors": factor_names,
        "factor_loadings": loadings,
        "estimation_days": len(common_pre),
        "event_window": list(event_window),
        "event_window_dates": window_dates,
        "observed_return": round(observed, 6),
        "counterfactual_return": round(counterfactual, 6),
        "effect": round(effect, 6),
        "pre_fit_rmse": round(pre_fit_rmse, 6),
    }


def default_factors_for_ticker(
    ticker: str,
    bars_by_ticker: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    factors: dict[str, list[dict[str, Any]]] = {}
    if "SPY" in bars_by_ticker:
        factors["SPY"] = bars_by_ticker["SPY"]
    if "QQQ" in bars_by_ticker:
        factors["QQQ"] = bars_by_ticker["QQQ"]
    etf = sector_etf_for(ticker)
    if etf and etf in bars_by_ticker:
        factors[etf] = bars_by_ticker[etf]
    return factors
