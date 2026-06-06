"""Digital advertising and ad-cycle macro mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import ANALYST_DOWNGRADE, GUIDANCE_CUT
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="ad_revenue_miss",
    reads=["fundamental_expectation", "investor_sentiment"],
    writes=["fundamental_expectation", "directional_pressure_score", "drawdown_risk_score"],
    emits=["digital_ad_slowdown", "guidance_cut"],
    version="v0.1",
)
def ad_revenue_miss(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    k.commit(
        e,
        {
            "fundamental_expectation": -0.14 * severity,
            "directional_pressure_score": 0.12 * severity,
            "drawdown_risk_score": 0.08 * severity,
        },
    )
    k.emit(
        "digital_ad_slowdown",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
    if float(e.payload.get("guidance_severity", severity * 0.7)) >= 0.5:
        if GUIDANCE_CUT not in k.flags:
            k.emit(
                "guidance_cut",
                payload={"severity": severity * 0.85},
                priority=1,
                cause=[f"event:{e.id}"],
                at_time=e.time + 2,
            )


@mechanism(
    kind="digital_ad_slowdown",
    reads=["sector_risk", "macro_risk_appetite"],
    writes=["sector_risk", "investor_sentiment", "directional_pressure_score"],
    emits=["macro_ad_budget_cut"],
    version="v0.1",
)
def digital_ad_slowdown(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.75))
    k.commit(
        e,
        {
            "sector_risk": 0.14 * severity,
            "investor_sentiment": -0.1 * severity,
            "directional_pressure_score": 0.09 * severity,
        },
    )
    k.emit(
        "macro_ad_budget_cut",
        payload={"severity": severity * 0.8},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="macro_ad_budget_cut",
    reads=["macro_risk_appetite", "fundamental_expectation"],
    writes=["macro_risk_appetite", "fundamental_expectation", "directional_pressure_score"],
    emits=["analyst_downgrade"],
    version="v0.1",
)
def macro_ad_budget_cut(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "macro_risk_appetite": -0.1 * severity,
            "fundamental_expectation": -0.08 * severity,
            "directional_pressure_score": 0.07 * severity,
        },
    )
    if ANALYST_DOWNGRADE not in k.flags:
        k.emit(
            "analyst_downgrade",
            payload={"severity": severity * 0.75},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 2,
        )
