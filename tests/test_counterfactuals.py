"""Tests for Phase 1 market counterfactuals."""

from __future__ import annotations

from market_causal_engine.counterfactuals.abnormal_return import estimate_abnormal_return
from market_causal_engine.counterfactuals.factor_model import estimate_factor_model
from market_causal_engine.counterfactuals.placebo import compute_placebo_rank
from market_causal_engine.counterfactuals.returns import cumulative_return, daily_simple_returns
from market_causal_engine.counterfactuals.synthetic_control import estimate_synthetic_control


def _bars_from_closes(closes: dict[str, float]) -> list[dict]:
    return [{"time": d, "close": c, "open": c} for d, c in sorted(closes.items())]


def _flat_series(start: str, n: int, *, daily_ret: float = 0.001) -> dict[str, float]:
    from datetime import datetime, timedelta

    dt = datetime.strptime(start, "%Y-%m-%d")
    price = 100.0
    closes: dict[str, float] = {}
    for i in range(n):
        d = (dt + timedelta(days=i)).strftime("%Y-%m-%d")
        if i > 0:
            price *= 1.0 + daily_ret
        closes[d] = price
    return closes


def test_cumulative_return():
    rets = {"2022-04-19": -0.25, "2022-04-20": -0.10}
    assert abs(cumulative_return(rets, ["2022-04-19", "2022-04-20"]) - (-0.325)) < 1e-6


def test_abnormal_return_effect():
    treated = _flat_series("2022-04-01", 30, daily_ret=0.002)
    treated["2022-04-19"] = treated["2022-04-18"] * 0.75
    treated["2022-04-20"] = treated["2022-04-19"] * 0.95
    market = _flat_series("2022-04-01", 30, daily_ret=0.001)
    out = estimate_abnormal_return(
        _bars_from_closes(treated),
        _bars_from_closes(market),
        "2022-04-19",
        event_window=(0, 1),
    )
    assert out["method"] == "abnormal_return"
    assert out["effect"] < -0.15


def test_synthetic_control_pre_fit_rmse():
    treated = _flat_series("2022-01-01", 200, daily_ret=0.001)
    c1 = _flat_series("2022-01-01", 200, daily_ret=0.001)
    c2 = _flat_series("2022-01-01", 200, daily_ret=0.0008)
    # Break perfect collinearity on event day only.
    d18 = sorted(treated.keys())[-2]
    d19 = sorted(treated.keys())[-1]
    treated[d19] = treated[d18] * 0.70
    out = estimate_synthetic_control(
        _bars_from_closes(treated),
        {"SPY": _bars_from_closes(c1), "QQQ": _bars_from_closes(c2)},
        d19,
        controls=["SPY", "QQQ"],
        event_window=(0, 0),
    )
    assert out["method"] == "synthetic_control"
    assert out["pre_fit_rmse"] < 0.01
    assert out["effect"] < -0.15


def test_factor_model_loadings():
    treated = _flat_series("2022-01-01", 200, daily_ret=0.0015)
    spy = _flat_series("2022-01-01", 200, daily_ret=0.001)
    qqq = _flat_series("2022-01-01", 200, daily_ret=0.0012)
    d18 = sorted(treated.keys())[-2]
    d19 = sorted(treated.keys())[-1]
    treated[d19] = treated[d18] * 0.80
    out = estimate_factor_model(
        _bars_from_closes(treated),
        {"SPY": _bars_from_closes(spy), "QQQ": _bars_from_closes(qqq)},
        d19,
        event_window=(0, 0),
    )
    assert "factor_loadings" in out
    assert out["pre_fit_rmse"] < 0.05


def test_placebo_rank():
    assert compute_placebo_rank(-0.30, [-0.01, -0.02, -0.05, -0.10, -0.25]) == 1.0
