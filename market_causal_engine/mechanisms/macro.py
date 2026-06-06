"""Macro event transmission: CPI, FOMC, NFP, yields, rotation, beta."""

from __future__ import annotations

from market_causal_engine.constants import (
    MACRO_SHOCK_ACTIVE,
    MACRO_SHOCK_SUPPRESSED,
    SECTOR_SPILLOVER,
    SECTOR_SPILLOVER_SUPPRESSED,
)
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


def _macro_shock_commit(k: Kernel, e: Event, severity: float) -> None:
    k.commit(
        e,
        {
            "macro_risk_appetite": -0.2 * severity,
            "valuation_pressure": 0.18 * severity,
            "directional_pressure_score": 0.14 * severity,
            "volatility_risk_score": 0.12 * severity,
        },
    )
    k.set_flag(MACRO_SHOCK_ACTIVE, e)


@mechanism(
    kind="macro_rate_shock",
    reads=["macro_risk_appetite", "fundamental_expectation"],
    writes=[
        "macro_risk_appetite",
        "valuation_pressure",
        "directional_pressure_score",
        "volatility_risk_score",
    ],
    emits=["bond_yield_reaction", "sector_spillover"],
    version="v0.1",
)
def macro_rate_shock(k: Kernel, e: Event) -> None:
    if MACRO_SHOCK_SUPPRESSED in k.flags:
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.75))
    _macro_shock_commit(k, e, severity)
    k.emit(
        "bond_yield_reaction",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
    if SECTOR_SPILLOVER_SUPPRESSED not in k.flags:
        k.emit(
            "sector_spillover",
            payload={"severity": severity * 0.8},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 2,
        )


@mechanism(
    kind="fomc_statement",
    reads=["macro_risk_appetite", "bond_yield_pressure"],
    writes=["macro_risk_appetite", "bond_yield_pressure", "volatility_risk_score"],
    emits=["bond_yield_reaction", "growth_value_rotation"],
    version="v0.1",
)
def fomc_statement(k: Kernel, e: Event) -> None:
    if MACRO_SHOCK_SUPPRESSED in k.flags:
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.8))
    hawkish = float(e.payload.get("hawkish", 0.7))
    _macro_shock_commit(k, e, severity * hawkish)
    k.commit(e, {"bond_yield_pressure": 0.2 * severity * hawkish})
    k.emit("bond_yield_reaction", payload={"severity": severity}, priority=1, cause=[f"event:{e.id}"], at_time=e.time + 1)
    k.emit(
        "growth_value_rotation",
        payload={"severity": severity, "direction": hawkish},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 2,
    )


@mechanism(
    kind="cpi_surprise",
    reads=["macro_risk_appetite", "bond_yield_pressure"],
    writes=["bond_yield_pressure", "macro_risk_appetite", "directional_pressure_score"],
    emits=["bond_yield_reaction", "sector_spillover"],
    version="v0.1",
)
def cpi_surprise(k: Kernel, e: Event) -> None:
    if MACRO_SHOCK_SUPPRESSED in k.flags:
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.75))
    hot = float(e.payload.get("hot_print", 0.8))
    k.commit(
        e,
        {
            "bond_yield_pressure": 0.18 * severity * hot,
            "macro_risk_appetite": -0.15 * severity * hot,
            "directional_pressure_score": 0.1 * severity,
        },
    )
    k.set_flag(MACRO_SHOCK_ACTIVE, e)
    k.emit("bond_yield_reaction", payload={"severity": severity * hot}, priority=1, cause=[f"event:{e.id}"], at_time=e.time + 1)
    if SECTOR_SPILLOVER_SUPPRESSED not in k.flags:
        k.emit("sector_spillover", payload={"severity": severity * 0.7}, priority=2, cause=[f"event:{e.id}"], at_time=e.time + 2)


@mechanism(
    kind="nfp_surprise",
    reads=["macro_risk_appetite"],
    writes=["macro_risk_appetite", "volatility_risk_score"],
    emits=["bond_yield_reaction"],
    version="v0.1",
)
def nfp_surprise(k: Kernel, e: Event) -> None:
    if MACRO_SHOCK_SUPPRESSED in k.flags:
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "macro_risk_appetite": -0.12 * severity,
            "volatility_risk_score": 0.1 * severity,
        },
    )
    k.emit("bond_yield_reaction", payload={"severity": severity * 0.8}, priority=1, cause=[f"event:{e.id}"], at_time=e.time + 1)


@mechanism(
    kind="bond_yield_reaction",
    reads=["bond_yield_pressure", "valuation_pressure"],
    writes=["valuation_pressure", "directional_pressure_score", "growth_value_tilt"],
    emits=["sector_spillover", "beta_transmission"],
    version="v0.1",
)
def bond_yield_reaction(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "valuation_pressure": 0.14 * severity,
            "directional_pressure_score": 0.1 * severity,
            "growth_value_tilt": 0.12 * severity,
        },
    )
    if SECTOR_SPILLOVER_SUPPRESSED not in k.flags:
        k.emit("sector_spillover", payload={"severity": severity * 0.75}, priority=2, cause=[f"event:{e.id}"], at_time=e.time + 1)
    k.emit("beta_transmission", payload={"severity": severity}, priority=2, cause=[f"event:{e.id}"], at_time=e.time + 2)


@mechanism(
    kind="growth_value_rotation",
    reads=["growth_value_tilt", "sector_risk"],
    writes=["growth_value_tilt", "sector_risk", "directional_pressure_score"],
    emits=["sector_etf_movement"],
    version="v0.1",
)
def growth_value_rotation(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    direction = float(e.payload.get("direction", 0.7))
    k.commit(
        e,
        {
            "growth_value_tilt": 0.15 * severity * direction,
            "sector_risk": 0.1 * severity,
            "directional_pressure_score": 0.08 * severity * direction,
        },
    )
    k.emit(
        "sector_etf_movement",
        payload={"severity": severity, "direction": direction},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="sector_spillover",
    reads=["sector_risk", "valuation_pressure"],
    writes=["sector_risk", "directional_pressure_score", "drawdown_risk_score"],
    emits=["beta_transmission"],
    version="v0.1",
)
def sector_spillover(k: Kernel, e: Event) -> None:
    if SECTOR_SPILLOVER_SUPPRESSED in k.flags:
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.6))
    k.commit(
        e,
        {
            "sector_risk": 0.18 * severity,
            "directional_pressure_score": 0.08 * severity,
            "drawdown_risk_score": 0.06 * severity,
        },
    )
    k.set_flag(SECTOR_SPILLOVER, e)
    k.emit("beta_transmission", payload={"severity": severity * 0.85}, priority=2, cause=[f"event:{e.id}"], at_time=e.time + 1)


@mechanism(
    kind="beta_transmission",
    reads=["stock_beta_exposure", "sector_risk"],
    writes=["directional_pressure_score", "drawdown_risk_score", "volatility_risk_score"],
    emits=["price_impact_amplified"],
    version="v0.1",
)
def beta_transmission(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    beta = max(0.3, k.state["stock_beta_exposure"])
    amp = severity * beta
    k.commit(
        e,
        {
            "directional_pressure_score": 0.12 * amp,
            "drawdown_risk_score": 0.1 * amp,
            "volatility_risk_score": 0.08 * amp,
        },
    )
    k.emit("price_impact_amplified", payload={"severity": amp}, priority=1, cause=[f"event:{e.id}"], at_time=e.time + 1)
