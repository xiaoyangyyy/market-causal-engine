"""Intraday market signals: volume, volatility, sector ETF."""

from __future__ import annotations

from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="intraday_volume_spike",
    reads=["liquidity_depth", "attention_intensity"],
    writes=["liquidity_stress_score", "attention_intensity"],
    emits=["price_impact_amplified"],
    version="v0.1",
)
def intraday_volume_spike(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    direction = float(e.payload.get("direction", 1.0))  # 1=sell pressure, -1=buy
    k.commit(
        e,
        {
            "liquidity_stress_score": 0.1 * severity,
            "attention_intensity": 0.08 * severity,
            "directional_pressure_score": 0.06 * severity * direction,
        },
    )
    k.emit(
        "price_impact_amplified",
        payload={"severity": severity * abs(direction), "direction": direction},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="intraday_volatility_spike",
    reads=["volatility_state"],
    writes=["volatility_state", "volatility_risk_score"],
    emits=["option_gamma_pressure"],
    version="v0.1",
)
def intraday_volatility_spike(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "volatility_state": 0.15 * severity,
            "volatility_risk_score": 0.12 * severity,
        },
    )
    k.emit(
        "option_gamma_pressure",
        payload={"severity": severity * 0.8},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="sector_etf_movement",
    reads=["sector_risk"],
    writes=["sector_risk", "directional_pressure_score"],
    emits=["institutional_rebalance"],
    version="v0.1",
)
def sector_etf_movement(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.6))
    direction = float(e.payload.get("direction", 1.0))
    k.commit(
        e,
        {
            "sector_risk": 0.12 * severity * abs(direction),
            "directional_pressure_score": 0.07 * severity * direction,
        },
    )
    if abs(direction) >= 0.5:
        k.emit(
            "institutional_rebalance",
            payload={"severity": severity * 0.7},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )
