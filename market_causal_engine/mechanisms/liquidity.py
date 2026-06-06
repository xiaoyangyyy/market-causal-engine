"""Liquidity and price-impact mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import LIQUIDITY_STRESS
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="liquidity_dry_up",
    reads=["liquidity_depth", "volatility_state"],
    writes=["liquidity_depth", "liquidity_stress_score", "volatility_risk_score"],
    emits=["price_impact_amplified"],
    resources=["market_maker_capacity"],
    version="v0.1",
)
def liquidity_dry_up(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    if not k.acquire("market_maker_capacity", 5 * severity, e):
        e.status = "blocked"
        return

    k.commit(
        e,
        {
            "liquidity_depth": -0.2 * severity,
            "liquidity_stress_score": 0.18 * severity,
            "volatility_risk_score": 0.1 * severity,
        },
    )
    k.set_flag(LIQUIDITY_STRESS, e)

    delay = int(k.prior("liquidity_dry_up", "emit_impact_delay", 1))
    k.emit(
        "price_impact_amplified",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="large_sell_order",
    reads=["liquidity_depth", "position_crowding"],
    writes=["directional_pressure_score", "liquidity_stress_score"],
    emits=["price_impact_amplified"],
    version="v0.1",
)
def large_sell_order(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    liq_factor = max(0.3, 1.0 - k.state["liquidity_depth"])
    amp = k.prior("large_sell_order", "impact_amplifier", 1.4)

    k.commit(
        e,
        {
            "directional_pressure_score": 0.12 * severity * liq_factor * amp,
            "liquidity_stress_score": 0.1 * severity * liq_factor,
        },
    )
    k.emit(
        "price_impact_amplified",
        payload={"severity": severity * liq_factor},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="price_impact_amplified",
    reads=["liquidity_depth", "option_gamma_exposure", "volatility_state"],
    writes=[
        "drawdown_risk_score",
        "directional_pressure_score",
        "volatility_risk_score",
    ],
    version="v0.1",
)
def price_impact_amplified(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    direction = float(e.payload.get("direction", 1.0))
    liq_factor = max(0.4, 1.2 - k.state["liquidity_depth"])
    gamma_factor = 1.0 + 0.3 * k.state["option_gamma_exposure"]

    k.commit(
        e,
        {
            "drawdown_risk_score": 0.15 * severity * liq_factor * gamma_factor * max(direction, 0),
            "directional_pressure_score": 0.08 * severity * liq_factor * direction,
            "volatility_risk_score": 0.06 * severity * gamma_factor,
        },
    )
