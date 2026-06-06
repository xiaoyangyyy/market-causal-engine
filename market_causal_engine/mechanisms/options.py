"""Options / gamma feedback mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import OPTION_GAMMA_ACTIVE, OPTION_GAMMA_SUPPRESSED
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="put_volume_spike",
    reads=["volatility_state", "attention_intensity"],
    writes=["option_gamma_exposure", "volatility_state"],
    emits=["option_gamma_pressure"],
    version="v0.1",
)
def put_volume_spike(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "option_gamma_exposure": 0.2 * severity,
            "volatility_state": 0.15 * severity,
        },
    )
    if OPTION_GAMMA_SUPPRESSED not in k.flags:
        k.emit(
            "option_gamma_pressure",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )


@mechanism(
    kind="option_gamma_pressure",
    reads=["option_gamma_exposure", "volatility_state"],
    writes=[
        "volatility_risk_score",
        "directional_pressure_score",
        "option_gamma_exposure",
    ],
    emits=["price_impact_amplified"],
    resources=["options_dealer_hedging_capacity"],
    version="v0.1",
)
def option_gamma_pressure(k: Kernel, e: Event) -> None:
    if OPTION_GAMMA_SUPPRESSED in k.flags:
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.7))
    if not k.acquire("options_dealer_hedging_capacity", 8 * severity, e):
        e.status = "blocked"
        return

    k.commit(
        e,
        {
            "volatility_risk_score": 0.14 * severity,
            "directional_pressure_score": 0.1 * severity,
            "option_gamma_exposure": 0.08 * severity,
        },
    )
    k.set_flag(OPTION_GAMMA_ACTIVE, e)

    k.emit(
        "price_impact_amplified",
        payload={"severity": severity * 1.2},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
