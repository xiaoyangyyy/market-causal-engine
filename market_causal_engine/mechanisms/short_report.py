"""Short-seller report impact mechanisms."""

from __future__ import annotations

from market_causal_engine.constants import SHORT_SQUEEZE_ACTIVE, SOCIAL_AMPLIFICATION_SUPPRESSED
from market_causal_engine.kernel import Event, Kernel
from market_causal_engine.registry import mechanism


@mechanism(
    kind="company_response",
    reads=["trust_level", "investor_sentiment"],
    writes=["trust_level", "investor_sentiment", "directional_pressure_score"],
    resources=["corporate_comm_channel"],
    emits=["reversal_signal"],
    version="v0.1",
)
def company_response(k: Kernel, e: Event) -> None:
    if not k.acquire("corporate_comm_channel", 1, e):
        e.status = "blocked"
        return

    credibility = float(e.payload.get("credibility", 0.5))
    strength = float(e.payload.get("strength", 0.6))
    trust_lift = k.prior("company_response", "trust_lift", 0.15) * credibility * strength
    sent_lift = k.prior("company_response", "sentiment_lift", 0.1) * credibility

    k.commit(
        e,
        {
            "trust_level": trust_lift,
            "investor_sentiment": sent_lift,
            "directional_pressure_score": -0.08 * credibility * strength,
        },
    )

    if credibility >= 0.65:
        k.emit(
            "reversal_signal",
            payload={"severity": credibility},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 2,
        )


@mechanism(
    kind="news_amplification",
    reads=["attention_intensity"],
    writes=["attention_intensity", "trust_level", "volatility_risk_score"],
    emits=["social_discussion_spike"],
    version="v0.1",
)
def news_amplification(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "attention_intensity": 0.15 * severity,
            "trust_level": -0.1 * severity,
            "volatility_risk_score": 0.08 * severity,
        },
    )
    if SOCIAL_AMPLIFICATION_SUPPRESSED not in k.flags:
        k.emit(
            "social_discussion_spike",
            payload={"severity": severity},
            priority=3,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )


@mechanism(
    kind="social_discussion_spike",
    reads=["attention_intensity", "position_crowding"],
    writes=["attention_intensity", "position_crowding", "directional_pressure_score"],
    emits=["liquidity_dry_up"],
    version="v0.1",
)
def social_discussion_spike(k: Kernel, e: Event) -> None:
    if SOCIAL_AMPLIFICATION_SUPPRESSED in k.flags:
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.7))
    squeeze_regime = k.state["short_interest_pressure"] > 0.65

    k.commit(
        e,
        {
            "attention_intensity": 0.14 * severity,
            "position_crowding": 0.12 * severity,
            "volatility_risk_score": 0.06 * severity,
            "directional_pressure_score": 0.0 if squeeze_regime else 0.09 * severity,
        },
    )
    if squeeze_regime:
        k.emit(
            "short_cover_risk",
            payload={"severity": severity},
            priority=1,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )
        return

    k.emit(
        "liquidity_dry_up",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="trust_erosion",
    reads=["trust_level", "investor_sentiment"],
    writes=["trust_level", "investor_sentiment", "drawdown_risk_score"],
    emits=["continuation_pressure"],
    version="v0.1",
)
def trust_erosion(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.75))
    k.commit(
        e,
        {
            "trust_level": -0.18 * severity,
            "investor_sentiment": -0.12 * severity,
            "drawdown_risk_score": 0.1 * severity,
        },
    )
    k.emit(
        "continuation_pressure",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + 1,
    )


@mechanism(
    kind="regulatory_probe",
    reads=["regulatory_risk"],
    writes=["regulatory_risk", "trust_level", "directional_pressure_score"],
    version="v0.1",
)
def regulatory_probe(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    k.commit(
        e,
        {
            "regulatory_risk": 0.22 * severity,
            "trust_level": -0.1 * severity,
            "directional_pressure_score": 0.1 * severity,
        },
    )


@mechanism(
    kind="continuation_pressure",
    reads=["trust_level", "short_interest_pressure"],
    writes=["directional_pressure_score", "drawdown_risk_score"],
    version="v0.1",
)
def continuation_pressure(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    k.commit(
        e,
        {
            "directional_pressure_score": 0.1 * severity,
            "drawdown_risk_score": 0.08 * severity,
        },
    )


@mechanism(
    kind="reversal_signal",
    reads=["short_interest_pressure", "trust_level"],
    writes=["directional_pressure_score", "volatility_risk_score"],
    emits=["short_cover_risk"],
    version="v0.1",
)
def reversal_signal(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.6))
    k.commit(
        e,
        {
            "directional_pressure_score": -0.12 * severity,
            "volatility_risk_score": 0.1 * severity,
        },
    )
    if k.state["short_interest_pressure"] > 0.4:
        k.emit(
            "short_cover_risk",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 1,
        )


@mechanism(
    kind="short_cover_risk",
    reads=["short_interest_pressure", "liquidity_depth"],
    writes=["directional_pressure_score", "volatility_risk_score"],
    version="v0.1",
)
def short_cover_risk(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.65))
    squeeze = k.state["short_interest_pressure"] * severity
    k.set_flag(SHORT_SQUEEZE_ACTIVE, e)
    k.commit(
        e,
        {
            "directional_pressure_score": -0.28 * squeeze,
            "volatility_risk_score": 0.14 * squeeze,
        },
    )
