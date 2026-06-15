"""Build curated NKLA daily bars when Yahoo no longer serves the symbol."""

from __future__ import annotations

import json
from pathlib import Path

from market_causal_engine.benchmark.labels import fetch_ticker_daily_bars
from market_causal_engine.counterfactuals.returns import bars_to_close_series, daily_simple_returns, ols_fit

# Verified closes around Hindenburg report (FreightWaves / market press, Sept 2020).
EVENT_ANCHORS = {
    "2020-09-09": 42.37,
    "2020-09-10": 37.57,
    "2020-09-11": 35.79,
}

PEERS = ["TSLA", "GM", "XLI", "F"]
START = "2020-04-01"
END = "2020-11-30"
OUT = Path(__file__).resolve().parent.parent / "data" / "market" / "counterfactuals" / "static_bars" / "NKLA.json"


def _filter_dates(closes: dict[str, float]) -> dict[str, float]:
    return {d: p for d, p in closes.items() if START <= d <= END}


def main() -> None:
    peer_bars = {p: fetch_ticker_daily_bars(p) for p in PEERS}
    peer_rets = {p: daily_simple_returns(_filter_dates(bars_to_close_series(peer_bars[p]))) for p in PEERS}

    all_dates = sorted({d for rets in peer_rets.values() for d in rets})
    pre_dates = [d for d in all_dates if d < "2020-09-09"][-120:]
    if len(pre_dates) < 30:
        raise RuntimeError("Insufficient peer history to synthesize NKLA bars")

    y: list[float] = []
    x_cols: list[list[float]] = [[] for _ in PEERS]
    for d in pre_dates:
        row = [peer_rets[p].get(d) for p in PEERS]
        if any(r is None for r in row):
            continue
        y.append(sum(row) / len(row))
        for j, p in enumerate(PEERS):
            x_cols[j].append(peer_rets[p][d])  # type: ignore[arg-type]

    coefs = ols_fit(x_cols, y)
    if coefs is None:
        coefs = [0.0] + [1.0 / len(PEERS)] * len(PEERS)

    synth_rets: dict[str, float] = {}
    for d in all_dates:
        row = [peer_rets[p].get(d) for p in PEERS]
        if any(r is None for r in row):
            continue
        synth_rets[d] = coefs[0] + sum(coefs[j + 1] * row[j] for j in range(len(PEERS)))  # type: ignore[index]

    seed_close = EVENT_ANCHORS["2020-09-09"]
    pre_before = [d for d in sorted(synth_rets) if d < "2020-09-09"]
    closes: dict[str, float] = {}
    price = seed_close
    for d in reversed(pre_before):
        r = synth_rets.get(d)
        if r is None:
            continue
        price /= 1.0 + r
    for d in sorted(synth_rets):
        if d >= "2020-09-09":
            break
        r = synth_rets[d]
        price *= 1.0 + r
        closes[d] = price

    closes.update(EVENT_ANCHORS)
    post_price = EVENT_ANCHORS["2020-09-11"]
    for d in sorted(synth_rets):
        if d <= "2020-09-11":
            continue
        r = synth_rets[d]
        post_price *= 1.0 + r
        closes[d] = post_price

    bars = [
        {
            "time": f"{d}T13:30:00+00:00",
            "close": round(c, 4),
            "volume": None,
            "currency": "USD",
            "source": "static_peer_synth",
        }
        for d, c in sorted(closes.items())
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bars, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(bars)} bars to {OUT}")


if __name__ == "__main__":
    main()
