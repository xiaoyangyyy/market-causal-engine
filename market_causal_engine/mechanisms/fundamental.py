"""Fundamental / earnings mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import (
    ANALYST_DOWNGRADE,
    ANALYST_DOWNGRADE_SUPPRESSED,
    EARNINGS_MISS,
    EARNINGS_RELEASED,
    GUIDANCE_CUT,
    INSTITUTIONAL_REBALANCE,
    LIQUIDITY_STRESS,
    OPTION_GAMMA_SUPPRESSED,
)
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="earnings_call_transcript",
    reads=["fundamental_expectation", "investor_sentiment"],
    writes=["fundamental_expectation", "investor_sentiment", "directional_pressure_score"],
    emits=["guidance_cut", "margin_pressure"],
    version="v0.1",
)
def earnings_call_transcript(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    tone = float(e.payload.get("tone", -0.5))
    k.commit(
        e,
        {
            "fundamental_expectation": -0.08 * severity * max(0, -tone),
            "investor_sentiment": 0.06 * tone * severity,
            "directional_pressure_score": 0.05 * max(0, -tone) * severity,
        },
    )
    if tone < -0.3:
        k.emit(
            "guidance_cut",
            payload={"severity": severity * abs(tone)},
            priority=1,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )


@mechanism(
    kind="earnings_beat",
    reads=["fundamental_expectation", "investor_sentiment"],
    writes=["fundamental_expectation", "investor_sentiment", "directional_pressure_score"],
    emits=["analyst_upgrade"],
    version="v0.1",
)
def earnings_beat(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    k.commit(
        e,
        {
            "fundamental_expectation": 0.12 * severity,
            "investor_sentiment": 0.1 * severity,
            "directional_pressure_score": -0.1 * severity,
        },
    )
    k.emit(
        "analyst_upgrade",
        payload={"severity": severity * 0.8},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
    k.emit(
        "sector_etf_movement",
        payload={"severity": severity * 0.6, "direction": -0.8},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 2,
    )


@mechanism(
    kind="analyst_upgrade",
    reads=["investor_sentiment"],
    writes=["investor_sentiment", "directional_pressure_score"],
    version="v0.1",
)
def analyst_upgrade(k: Kernel, e: Event) -> None:
    if not k.acquire("analyst_coverage_channel", 1, e):
        e.status = "blocked"
        return
    severity = float(e.payload.get("severity", 0.6))
    k.commit(
        e,
        {
            "investor_sentiment": 0.12 * severity,
            "directional_pressure_score": -0.08 * severity,
        },
    )


@mechanism(
    kind="analyst_rating_change",
    reads=["investor_sentiment", "attention_intensity"],
    writes=["investor_sentiment", "attention_intensity"],
    version="v0.1",
)
def analyst_rating_change(k: Kernel, e: Event) -> None:
    direction = float(e.payload.get("direction", -1.0))
    severity = float(e.payload.get("severity", 0.7))
    if direction < 0:
        k.emit(
            "analyst_downgrade",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time,
        )
    else:
        k.emit(
            "analyst_upgrade",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time,
        )


@mechanism(
    kind="earnings_release",
    reads=["fundamental_expectation", "attention_intensity"],
    writes=["attention_intensity"],
    emits=["earnings_miss", "earnings_beat"],
    version="v0.1",
)
def earnings_release(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(e, {"attention_intensity": 0.15 * severity})
    k.set_flag(EARNINGS_RELEASED, e)

    miss_prob = float(e.payload.get("miss_severity", severity))
    beat_prob = float(e.payload.get("beat_severity", 0.0))
    if beat_prob >= 0.5:
        delay = int(k.prior("earnings_release", "emit_beat_delay", 1))
        k.emit(
            "earnings_beat",
            payload={"severity": beat_prob},
            priority=1,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )
    elif miss_prob >= 0.4:
        delay = int(k.prior("earnings_release", "emit_miss_delay", 1))
        k.emit(
            "earnings_miss",
            payload={
                "severity": miss_prob,
                "guidance_severity": float(e.payload.get("guidance_severity", miss_prob)),
            },
            priority=1,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )


@mechanism(
    kind="earnings_miss",
    reads=["fundamental_expectation", "valuation_pressure"],
    writes=["fundamental_expectation", "valuation_pressure", "directional_pressure_score"],
    emits=["guidance_cut"],
    version="v0.1",
)
def earnings_miss(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.6))
    fund_delta = k.prior("earnings_miss", "fundamental_delta", -0.12)
    val_delta = k.prior("earnings_miss", "valuation_delta", 0.15)
    dir_delta = k.prior("earnings_miss", "directional_delta", 0.08)

    k.commit(
        e,
        {
            "fundamental_expectation": fund_delta * severity,
            "valuation_pressure": val_delta * severity,
            "directional_pressure_score": dir_delta * severity,
        },
    )
    k.set_flag(EARNINGS_MISS, e)

    guidance_severity = float(e.payload.get("guidance_severity", severity))
    if guidance_severity >= 0.5:
        delay = int(k.prior("earnings_miss", "emit_guidance_delay", 1))
        k.emit(
            "guidance_cut",
            payload={"severity": guidance_severity},
            priority=1,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )


@mechanism(
    kind="guidance_cut",
    reads=["fundamental_expectation", "valuation_pressure"],
    writes=[
        "fundamental_expectation",
        "valuation_pressure",
        "directional_pressure_score",
        "drawdown_risk_score",
    ],
    emits=["analyst_downgrade"],
    version="v0.1",
)
def guidance_cut(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.75))
    fund_delta = k.prior("guidance_cut", "fundamental_delta", -0.22)
    val_delta = k.prior("guidance_cut", "valuation_delta", 0.28)
    dir_delta = k.prior("guidance_cut", "directional_delta", 0.18)
    dd_delta = k.prior("guidance_cut", "drawdown_delta", 0.12)

    k.commit(
        e,
        {
            "fundamental_expectation": fund_delta * severity,
            "valuation_pressure": val_delta * severity,
            "directional_pressure_score": dir_delta * severity,
            "drawdown_risk_score": dd_delta * severity,
        },
    )
    k.set_flag(GUIDANCE_CUT, e)

    if ANALYST_DOWNGRADE_SUPPRESSED not in k.flags:
        delay = int(k.prior("guidance_cut", "emit_downgrade_delay", 1))
        k.emit(
            "analyst_downgrade",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )


@mechanism(
    kind="analyst_downgrade",
    reads=["investor_sentiment", "attention_intensity"],
    writes=["investor_sentiment", "attention_intensity", "directional_pressure_score"],
    emits=["institutional_rebalance"],
    version="v0.1",
)
def analyst_downgrade(k: Kernel, e: Event) -> None:
    if ANALYST_DOWNGRADE_SUPPRESSED in k.flags:
        e.status = "blocked"
        return

    if not k.acquire("analyst_coverage_channel", 1, e):
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.7))
    sent_delta = k.prior("analyst_downgrade", "sentiment_delta", -0.18)
    attn_delta = k.prior("analyst_downgrade", "attention_delta", 0.12)
    dir_delta = k.prior("analyst_downgrade", "directional_delta", 0.1)

    k.commit(
        e,
        {
            "investor_sentiment": sent_delta * severity,
            "attention_intensity": attn_delta * severity,
            "directional_pressure_score": dir_delta * severity,
        },
    )
    k.set_flag(ANALYST_DOWNGRADE, e)

    delay = int(k.prior("analyst_downgrade", "emit_rebalance_delay", 1))
    k.emit(
        "institutional_rebalance",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="institutional_rebalance",
    reads=["liquidity_depth", "position_crowding"],
    writes=[
        "liquidity_depth",
        "liquidity_stress_score",
        "directional_pressure_score",
        "drawdown_risk_score",
    ],
    emits=["option_gamma_pressure"],
    version="v0.1",
)
def institutional_rebalance(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    liq_delta = k.prior("institutional_rebalance", "liquidity_delta", -0.15)
    stress_delta = k.prior("institutional_rebalance", "stress_delta", 0.14)
    dir_delta = k.prior("institutional_rebalance", "directional_delta", 0.12)
    dd_delta = k.prior("institutional_rebalance", "drawdown_delta", 0.1)

    k.commit(
        e,
        {
            "liquidity_depth": liq_delta * severity,
            "liquidity_stress_score": stress_delta * severity,
            "directional_pressure_score": dir_delta * severity,
            "drawdown_risk_score": dd_delta * severity,
        },
    )
    k.set_flag(INSTITUTIONAL_REBALANCE, e)

    if k.state["liquidity_depth"] < 0.45:
        k.set_flag(LIQUIDITY_STRESS, e)

    if OPTION_GAMMA_SUPPRESSED not in k.flags:
        delay = int(k.prior("institutional_rebalance", "emit_gamma_delay", 1))
        k.emit(
            "option_gamma_pressure",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )


@mechanism(
    kind="margin_pressure",
    reads=["fundamental_expectation", "valuation_pressure"],
    writes=["valuation_pressure", "directional_pressure_score"],
    version="v0.1",
)
def margin_pressure(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.6))
    k.commit(
        e,
        {
            "valuation_pressure": 0.12 * severity,
            "directional_pressure_score": 0.08 * severity,
        },
    )
