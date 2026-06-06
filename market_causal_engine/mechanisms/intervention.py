"""Market interventions and counterfactual gates."""

from __future__ import annotations

from market_causal_engine.constants import (
    ANALYST_DOWNGRADE_SUPPRESSED,
    GUIDANCE_CUT,
    LIQUIDITY_STRESS,
    MACRO_SHOCK_SUPPRESSED,
    OPTION_GAMMA_ACTIVE,
    OPTION_GAMMA_SUPPRESSED,
    RETAIL_ATTENTION_SPIKE,
    SECTOR_SPILLOVER_SUPPRESSED,
    SOCIAL_AMPLIFICATION_SUPPRESSED,
)
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="suppress_analyst_downgrade",
    reads=[],
    writes=[],
    version="v0.1",
)
def suppress_analyst_downgrade(k: Kernel, e: Event) -> None:
    k.set_flag(ANALYST_DOWNGRADE_SUPPRESSED, e)


@mechanism(
    kind="suppress_social_amplification",
    reads=[],
    writes=[],
    version="v0.1",
)
def suppress_social_amplification(k: Kernel, e: Event) -> None:
    k.set_flag(SOCIAL_AMPLIFICATION_SUPPRESSED, e)


@mechanism(
    kind="suppress_option_gamma",
    reads=[],
    writes=[],
    version="v0.1",
)
def suppress_option_gamma(k: Kernel, e: Event) -> None:
    k.set_flag(OPTION_GAMMA_SUPPRESSED, e)
    if OPTION_GAMMA_ACTIVE in k.flags:
        k.clear_flag(OPTION_GAMMA_ACTIVE, e)


@mechanism(
    kind="suppress_sector_spillover",
    reads=[],
    writes=[],
    version="v0.1",
)
def suppress_sector_spillover(k: Kernel, e: Event) -> None:
    k.set_flag(SECTOR_SPILLOVER_SUPPRESSED, e)


@mechanism(
    kind="suppress_macro_shock",
    reads=[],
    writes=[],
    version="v0.1",
)
def suppress_macro_shock(k: Kernel, e: Event) -> None:
    k.set_flag(MACRO_SHOCK_SUPPRESSED, e)


@mechanism(
    kind="company_clarification",
    reads=["investor_sentiment", "valuation_pressure", "attention_intensity"],
    writes=["investor_sentiment", "valuation_pressure", "directional_pressure_score"],
    resources=["corporate_comm_channel"],
    version="v0.1",
)
def company_clarification(k: Kernel, e: Event) -> None:
    if not k.acquire("corporate_comm_channel", 1, e):
        e.status = "blocked"
        return

    credibility = float(e.payload.get("credibility", 0.65))
    sent_lift = k.prior("company_clarification", "sentiment_lift", 0.12)
    val_relief = k.prior("company_clarification", "valuation_relief", 0.1)
    dir_relief = k.prior("company_clarification", "directional_relief", 0.08)

    k.commit(
        e,
        {
            "investor_sentiment": sent_lift * credibility,
            "valuation_pressure": -val_relief * credibility,
            "directional_pressure_score": -dir_relief * credibility,
        },
    )
    if GUIDANCE_CUT in k.flags and credibility >= 0.55:
        k.commit(
            e,
            {
                "drawdown_risk_score": -0.18 * credibility,
                "directional_pressure_score": -0.14 * credibility,
                "volatility_risk_score": -0.1 * credibility,
                "liquidity_stress_score": -0.08 * credibility,
            },
        )


@mechanism(
    kind="buyback_announcement",
    reads=["investor_sentiment", "directional_pressure_score"],
    writes=["investor_sentiment", "directional_pressure_score", "drawdown_risk_score"],
    version="v0.1",
)
def buyback_announcement(k: Kernel, e: Event) -> None:
    size = float(e.payload.get("size_factor", 0.5))
    k.commit(
        e,
        {
            "investor_sentiment": 0.08 * size,
            "directional_pressure_score": -0.1 * size,
            "drawdown_risk_score": -0.08 * size,
        },
    )


@mechanism(
    kind="liquidity_support",
    reads=["liquidity_depth", "liquidity_stress_score"],
    writes=["liquidity_depth", "liquidity_stress_score"],
    resources=["market_maker_capacity"],
    version="v0.1",
)
def liquidity_support(k: Kernel, e: Event) -> None:
    if not k.acquire("market_maker_capacity", 15, e):
        e.status = "blocked"
        return

    boost = k.prior("liquidity_support", "depth_boost", 0.25)
    stress_relief = k.prior("liquidity_support", "stress_relief", 0.15)

    k.commit(
        e,
        {
            "liquidity_depth": boost,
            "liquidity_stress_score": -stress_relief,
        },
    )
    if k.state["liquidity_depth"] >= 0.5 and LIQUIDITY_STRESS in k.flags:
        k.clear_flag(LIQUIDITY_STRESS, e)


@mechanism(
    kind="trading_halt",
    reads=["volatility_risk_score", "drawdown_risk_score"],
    writes=["volatility_risk_score", "liquidity_stress_score"],
    resources=["circuit_breaker_buffer"],
    version="v0.1",
)
def trading_halt(k: Kernel, e: Event) -> None:
    if not k.acquire("circuit_breaker_buffer", 1, e):
        e.status = "blocked"
        return

    k.commit(
        e,
        {
            "volatility_risk_score": -0.08,
            "liquidity_stress_score": -0.05,
        },
    )


@mechanism(
    kind="boost_liquidity_resource",
    reads=[],
    writes=["liquidity_depth"],
    version="v0.1",
)
def boost_liquidity_resource(k: Kernel, e: Event) -> None:
    """Counterfactual W4: pre-load deeper liquidity pool."""
    boost = float(e.payload.get("boost", 0.2))
    k.resources["market_maker_capacity"] = k.resources.get("market_maker_capacity", 0) + 30
    k.commit(e, {"liquidity_depth": boost})
