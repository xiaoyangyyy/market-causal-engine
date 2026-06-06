"""Match-layer mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import (
    CONTROVERSIAL_CALL_VISIBLE,
    HEAT_STRESS_HIGH,
    MATCH_HIGH_TENSION,
    TEAM_ELIMINATED,
)
from worldcup_causal_engine.kernel import Event, Kernel
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="controversial_call",
    reads=["match_tension", "perceived_unfairness"],
    writes=["match_tension", "perceived_unfairness"],
    emits=["viral_clip_published"],
    version="v0.1",
)
def controversial_call(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    unfairness_delta = k.prior("controversial_call", "unfairness_delta", 0.35)
    tension_delta = k.prior("controversial_call", "tension_delta", 0.25)
    delay = int(k.prior("controversial_call", "emit_viral_clip_delay", 3))

    k.commit(
        e,
        {
            "perceived_unfairness": unfairness_delta * severity,
            "match_tension": tension_delta * severity,
        },
    )
    k.set_flag(CONTROVERSIAL_CALL_VISIBLE, e)
    if k.state["match_tension"] >= 0.5:
        k.set_flag(MATCH_HIGH_TENSION, e)

    k.emit(
        "viral_clip_published",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="team_eliminated",
    reads=["humiliation_level", "match_tension"],
    writes=["humiliation_level", "match_tension"],
    emits=["fans_gather", "bar_district_pressure"],
    version="v0.1",
)
def team_eliminated(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.9))
    humiliation_delta = k.prior("team_eliminated", "humiliation_delta", 0.5)
    tension_delta = k.prior("team_eliminated", "tension_delta", 0.2)

    k.commit(
        e,
        {
            "humiliation_level": humiliation_delta * severity,
            "match_tension": tension_delta * severity,
        },
    )
    k.set_flag(TEAM_ELIMINATED, e)

    gather_delay = int(k.prior("team_eliminated", "emit_gather_delay", 2))
    k.emit(
        "fans_gather",
        payload={"severity": severity, "source": "elimination"},
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + gather_delay,
    )


@mechanism(
    kind="match_end",
    reads=["crowd_density", "transit_pressure", "heat_stress"],
    writes=[],
    emits=["fans_gather", "transit_delay"],
    version="v0.1",
)
def match_end(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 1.0))
    gather_delay = int(k.prior("match_end", "emit_gather_delay", 1))
    transit_delay_min = int(k.prior("match_end", "emit_transit_delay", 3))

    k.emit(
        "fans_gather",
        payload={"severity": severity, "source": "match_end"},
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + gather_delay,
    )

    if k.state["heat_stress"] >= k.prior("heat_stress_check", "threshold", 0.7):
        k.set_flag(HEAT_STRESS_HIGH, e)

    if k.state["transit_pressure"] >= k.prior("transit_delay", "pressure_threshold", 0.5):
        k.emit(
            "transit_delay",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + transit_delay_min,
        )
