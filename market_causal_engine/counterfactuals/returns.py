"""Daily return series alignment and event-window math (stdlib only)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def bars_to_close_series(bars: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for bar in bars:
        d = str(bar["time"])[:10]
        close = float(bar.get("close") or bar.get("open") or 0)
        if close > 0:
            out[d] = close
    return out


def daily_simple_returns(closes: dict[str, float]) -> dict[str, float]:
    """Date -> simple return vs previous trading day."""
    dates = sorted(closes)
    rets: dict[str, float] = {}
    for i in range(1, len(dates)):
        prev, cur = dates[i - 1], dates[i]
        p0, p1 = closes[prev], closes[cur]
        if p0 > 0:
            rets[cur] = (p1 - p0) / p0
    return rets


def prev_trading_date(closes: dict[str, float], event_date: str, *, max_lookback: int = 10) -> str | None:
    try:
        dt = datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return None
    for i in range(1, max_lookback + 1):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in closes:
            return d
    return None


def event_window_dates(
    closes: dict[str, float],
    event_date: str,
    *,
    window: tuple[int, int] = (0, 1),
) -> list[str]:
    """Trading dates from event_date through +window[1] sessions (inclusive)."""
    if event_date not in closes:
        return []
    dates = sorted(closes)
    idx = dates.index(event_date)
    end = min(len(dates) - 1, idx + window[1])
    return dates[idx : end + 1]


def cumulative_return(rets: dict[str, float], dates: list[str]) -> float | None:
    if not dates:
        return None
    acc = 1.0
    for d in dates:
        if d not in rets:
            return None
        acc *= 1.0 + rets[d]
    return acc - 1.0


def pre_estimation_dates(
    closes: dict[str, float],
    event_date: str,
    *,
    est_days: int = 120,
    gap_days: int = 5,
) -> list[str]:
    """Trading days in [event - est_days - gap, event - gap) before the event."""
    dates = sorted(closes)
    if event_date not in dates:
        return []
    idx = dates.index(event_date)
    end = max(0, idx - gap_days)
    start = max(0, end - est_days)
    return dates[start:end]


def align_series(
    series: dict[str, dict[str, float]],
    dates: list[str],
) -> tuple[list[str], list[list[float]]]:
    """Drop dates missing any series; return common dates and row vectors per series key order."""
    keys = list(series.keys())
    common = [d for d in dates if all(d in series[k] for k in keys)]
    rows = [[series[k][d] for d in common] for k in keys]
    return common, rows


def rmse(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return float("nan")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / len(a))


def solve_linear_system(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gaussian elimination for small dense systems."""
    n = len(a)
    if n == 0 or len(b) != n:
        return None
    aug = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = col
        for r in range(col + 1, n):
            if abs(aug[r][col]) > abs(aug[pivot][col]):
                pivot = r
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if abs(factor) < 1e-15:
                continue
            for j in range(col, n + 1):
                aug[r][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def ols_fit(x_cols: list[list[float]], y: list[float], *, ridge: float = 1e-8) -> list[float] | None:
    """OLS with intercept: y ~ 1 + X. x_cols each length T."""
    if not y or not x_cols:
        return None
    t = len(y)
    if any(len(c) != t for c in x_cols):
        return None
    k = len(x_cols)
    # Normal equations (X'X) beta = X'y, X = [1, x1, x2, ...]
    dim = k + 1
    xtx = [[0.0] * dim for _ in range(dim)]
    xty = [0.0] * dim
    for i in range(t):
        row = [1.0] + [x_cols[j][i] for j in range(k)]
        for r in range(dim):
            xty[r] += row[r] * y[i]
            for c in range(dim):
                xtx[r][c] += row[r] * row[c]
    for i in range(dim):
        xtx[i][i] += ridge
    return solve_linear_system(xtx, xty)
