"""Intervention mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import (
    DEESCALATION_ACTIVE,
    FAN_FLOWS_SEPARATED,
    OPPOSING_FANS_COLOCATED,
    RUMOR_SPIKE,
    TRANSIT_DELAY_ACTIVE,
)
from worldcup_causal_engine.kernel import Event, Kernel
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="official_clarification",
    reads=["rumor_volume", "outrage_frame"],
    writes=["rumor_volume", "outrage_frame"],
    resources=["official_comm_channel"],
    version="v0.1",
)
def official_clarification(k: Kernel, e: Event) -> None:
    if not k.acquire("official_comm_channel", 1, e):
        e.status = "blocked"
        return

    credibility = float(e.payload.get("credibility", 0.7))
    base_reduction = k.prior("official_clarification", "rumor_reduction", 0.25)
    multiplier = k.prior("official_clarification", "credibility_multiplier", 0.7)
    reduction = base_reduction * credibility * multiplier

    k.commit(
        e,
        {
            "rumor_volume": -reduction,
            "outrage_frame": -0.1 * credibility,
        },
    )

    if k.state["rumor_volume"] < k.prior("rumor_amplified", "rumor_spike_threshold", 0.6):
        k.clear_flag(RUMOR_SPIKE, e)


@mechanism(
    kind="team_captain_message",
    reads=["outrage_frame", "verbal_conflict_risk"],
    writes=["outrage_frame", "verbal_conflict_risk", "blame_frame"],
    version="v0.1",
)
def team_captain_message(k: Kernel, e: Event) -> None:
    credibility = float(e.payload.get("credibility", 0.6))
    outrage_reduction = k.prior("team_captain_message", "outrage_reduction", 0.2)
    verbal_reduction = k.prior("team_captain_message", "verbal_reduction", 0.15)

    k.commit(
        e,
        {
            "outrage_frame": -outrage_reduction * credibility,
            "blame_frame": -0.1 * credibility,
            "verbal_conflict_risk": -verbal_reduction * credibility,
        },
    )


@mechanism(
    kind="separate_fan_flows",
    reads=["crowd_density"],
    writes=["crowd_density"],
    resources=["police_units"],
    version="v0.1",
)
def separate_fan_flows(k: Kernel, e: Event) -> None:
    if not k.acquire("police_units", 5, e):
        e.status = "blocked"
        return

    k.set_flag(FAN_FLOWS_SEPARATED, e)
    if OPPOSING_FANS_COLOCATED in k.flags:
        k.clear_flag(OPPOSING_FANS_COLOCATED, e)

    k.commit(e, {"crowd_density": -0.05})


@mechanism(
    kind="transit_reroute",
    reads=["transit_pressure"],
    writes=["transit_pressure", "crowd_density"],
    resources=["transport_capacity"],
    version="v0.1",
)
def transit_reroute(k: Kernel, e: Event) -> None:
    amount = k.prior("transit_reroute", "capacity_cost", 200)
    if not k.acquire("transport_capacity", amount, e):
        e.status = "blocked"
        return

    reduction = k.prior("transit_reroute", "pressure_reduction", 0.3)
    k.commit(e, {"transit_pressure": -reduction, "crowd_density": -0.08})
    k.clear_flag(TRANSIT_DELAY_ACTIVE, e)


@mechanism(
    kind="deploy_deescalation",
    reads=["deescalation_capacity", "verbal_conflict_risk"],
    writes=["deescalation_capacity", "verbal_conflict_risk", "scuffle_risk"],
    resources=["deescalation_teams"],
    version="v0.1",
)
def deploy_deescalation(k: Kernel, e: Event) -> None:
    teams = k.prior("deploy_deescalation", "teams_required", 3)
    if not k.acquire("deescalation_teams", teams, e):
        e.status = "blocked"
        return

    capacity_boost = k.prior("deploy_deescalation", "capacity_boost", 0.25)
    verbal_reduction = k.prior("deploy_deescalation", "verbal_reduction", 0.2)
    scuffle_reduction = k.prior("deploy_deescalation", "scuffle_reduction", 0.1)

    k.commit(
        e,
        {
            "deescalation_capacity": capacity_boost,
            "verbal_conflict_risk": -verbal_reduction,
            "scuffle_risk": -scuffle_reduction,
        },
    )
    k.set_flag(DEESCALATION_ACTIVE, e)


@mechanism(
    kind="platform_rumor_throttle",
    reads=["rumor_volume", "misinfo_confidence", "platform_velocity"],
    writes=["rumor_volume", "misinfo_confidence", "platform_velocity"],
    resources=["fact_check_capacity"],
    version="v0.1",
)
def platform_rumor_throttle(k: Kernel, e: Event) -> None:
    """W6: platform/media reduces rumor spread via fact-check capacity."""
    if not k.acquire("fact_check_capacity", 3, e):
        e.status = "blocked"
        return

    strength = float(e.payload.get("strength", 0.7))
    k.commit(
        e,
        {
            "rumor_volume": -0.3 * strength,
            "misinfo_confidence": -0.25 * strength,
            "platform_velocity": -0.15 * strength,
        },
    )
    if k.state["rumor_volume"] < k.prior("rumor_amplified", "rumor_spike_threshold", 0.6):
        k.clear_flag(RUMOR_SPIKE, e)
