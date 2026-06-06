"""Sentiment and attention mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import (
    RETAIL_ATTENTION_SPIKE,
    SOCIAL_AMPLIFICATION_SUPPRESSED,
)
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="viral_negative_news",
    reads=["attention_intensity", "investor_sentiment"],
    writes=["attention_intensity", "investor_sentiment", "volatility_risk_score"],
    emits=["retail_attention_spike"],
    version="v0.1",
)
def viral_negative_news(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "attention_intensity": 0.2 * severity,
            "investor_sentiment": -0.1 * severity,
            "volatility_risk_score": 0.08 * severity,
        },
    )
    if SOCIAL_AMPLIFICATION_SUPPRESSED not in k.flags:
        delay = int(k.prior("viral_negative_news", "emit_retail_delay", 1))
        k.emit(
            "retail_attention_spike",
            payload={"severity": severity},
            priority=3,
            cause=[f"event:{e.id}"],
            at_time=e.time + delay,
        )


@mechanism(
    kind="retail_attention_spike",
    reads=["attention_intensity", "position_crowding"],
    writes=[
        "attention_intensity",
        "position_crowding",
        "volatility_risk_score",
        "directional_pressure_score",
    ],
    emits=["liquidity_dry_up"],
    version="v0.1",
)
def retail_attention_spike(k: Kernel, e: Event) -> None:
    if SOCIAL_AMPLIFICATION_SUPPRESSED in k.flags:
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.75))
    k.commit(
        e,
        {
            "attention_intensity": 0.18 * severity,
            "position_crowding": 0.15 * severity,
            "volatility_risk_score": 0.12 * severity,
            "directional_pressure_score": 0.1 * severity,
        },
    )
    k.set_flag(RETAIL_ATTENTION_SPIKE, e)

    delay = int(k.prior("retail_attention_spike", "emit_liquidity_delay", 1))
    k.emit(
        "liquidity_dry_up",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="short_seller_report",
    reads=["investor_sentiment", "short_interest_pressure", "trust_level"],
    writes=["investor_sentiment", "short_interest_pressure", "attention_intensity", "trust_level"],
    emits=["trust_erosion", "news_amplification"],
    version="v0.1",
)
def short_seller_report(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    k.commit(
        e,
        {
            "investor_sentiment": -0.15 * severity,
            "short_interest_pressure": 0.2 * severity,
            "attention_intensity": 0.12 * severity,
            "trust_level": -0.12 * severity,
        },
    )
    k.emit(
        "trust_erosion",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
    k.emit(
        "news_amplification",
        payload={"severity": severity * 0.9},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )
