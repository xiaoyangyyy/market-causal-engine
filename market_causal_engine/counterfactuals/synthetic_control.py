"""Synthetic control via pre-period return matching."""

from __future__ import annotations

from typing import Any

from market_causal_engine.counterfactuals.returns import (
    bars_to_close_series,
    cumulative_return,
    daily_simple_returns,
    event_window_dates,
    pre_estimation_dates,
    rmse,
    solve_linear_system,
)


def _fit_sc_weights(treated_pre: list[float], controls_pre: list[list[float]]) -> list[float] | None:
    """
    Constrained-ish SC weights: OLS with sum-to-one via reparameterization.
    controls_pre: k series each length T.
    Returns k weights (non-negative when possible via simplex projection).
    """
    k = len(controls_pre)
    if k == 0:
        return None
    t = len(treated_pre)
    if t == 0 or any(len(c) != t for c in controls_pre):
        return None

    if k == 1:
        return [1.0]

    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    ridge = 1e-8
    for i in range(t):
        for r in range(k):
            xty[r] += controls_pre[r][i] * treated_pre[i]
            for c in range(k):
                xtx[r][c] += controls_pre[r][i] * controls_pre[c][i]
    for i in range(k):
        xtx[i][i] += ridge
    return solve_weights_simplex(xty, xtx)


def solve_weights_simplex(xty: list[float], xtx: list[list[float]]) -> list[float] | None:
    """Project unconstrained solution onto simplex (w>=0, sum w = 1)."""
    w = solve_linear_system(xtx, xty)
    if w is None:
        return None
    w = [max(0.0, x) for x in w]
    s = sum(w)
    if s <= 1e-12:
        return [1.0 / len(w)] * len(w)
    return [x / s for x in w]


def estimate_synthetic_control(
    treated_bars: list[dict[str, Any]],
    control_bars: dict[str, list[dict[str, Any]]],
    event_date: str,
    *,
    controls: list[str],
    event_window: tuple[int, int] = (0, 1),
    est_days: int = 120,
) -> dict[str, Any]:
    treated_closes = bars_to_close_series(treated_bars)
    treated_rets = daily_simple_returns(treated_closes)
    control_rets: dict[str, dict[str, float]] = {
        sym: daily_simple_returns(bars_to_close_series(control_bars[sym])) for sym in controls if sym in control_bars
    }
    usable = [sym for sym in controls if sym in control_rets]
    if not usable:
        raise ValueError("No usable control tickers")

    pre_dates = pre_estimation_dates(treated_closes, event_date, est_days=est_days)
    common_pre = [
        d
        for d in pre_dates
        if d in treated_rets and all(d in control_rets[s] for s in usable)
    ]
    if len(common_pre) < 30:
        raise ValueError(f"Insufficient pre-period overlap ({len(common_pre)} days)")

    y = [treated_rets[d] for d in common_pre]
    x_cols = [[control_rets[s][d] for d in common_pre] for s in usable]
    weights = _fit_sc_weights(y, x_cols)
    if weights is None:
        raise ValueError("Synthetic control weight fit failed")

    fitted = [sum(weights[i] * x_cols[i][j] for i in range(len(usable))) for j in range(len(common_pre))]
    pre_fit_rmse = rmse(y, fitted)

    window_dates = event_window_dates(treated_closes, event_date, window=event_window)
    observed = cumulative_return(treated_rets, window_dates)
    if observed is None:
        raise ValueError("Missing treated event-window returns")

    acc = 1.0
    for d in window_dates:
        daily_cf = sum(weights[i] * control_rets[usable[i]][d] for i in range(len(usable)))
        acc *= 1.0 + daily_cf
    counterfactual = acc - 1.0
    effect = observed - counterfactual

    return {
        "method": "synthetic_control",
        "controls": usable,
        "control_weights": {usable[i]: round(weights[i], 6) for i in range(len(usable))},
        "estimation_days": len(common_pre),
        "event_window": list(event_window),
        "event_window_dates": window_dates,
        "observed_return": round(observed, 6),
        "counterfactual_return": round(counterfactual, 6),
        "effect": round(effect, 6),
        "pre_fit_rmse": round(pre_fit_rmse, 6),
    }
