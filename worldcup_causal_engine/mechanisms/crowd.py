"""Crowd and offline-risk mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import (
    CROWD_DENSITY_HIGH,
    FAN_FLOWS_SEPARATED,
    OPPOSING_FANS_COLOCATED,
    RUMOR_SPIKE,
    TEAM_ELIMINATED,
    TRANSIT_DELAY_ACTIVE,
)
from worldcup_causal_engine.kernel import Event, Kernel, TraceEntry
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="offline_mood_shift",
    reads=["verbal_conflict_risk", "rumor_volume"],
    writes=["verbal_conflict_risk"],
    waits=[RUMOR_SPIKE],
    emits=["opposing_fans_contact"],
    version="v0.1",
)
def offline_mood_shift(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    verbal_delta = k.prior("offline_mood_shift", "verbal_risk_delta", 0.15)
    delay = int(k.prior("offline_mood_shift", "emit_contact_delay", 10))

    k.commit(e, {"verbal_conflict_risk": verbal_delta * severity})

    k.emit(
        "opposing_fans_contact",
        payload={"severity": severity},
        delay=delay,
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="opposing_fans_contact",
    reads=["crowd_density", "rumor_volume"],
    writes=["verbal_conflict_risk"],
    emits=["verbal_conflict"],
    version="v0.1",
)
def opposing_fans_contact(k: Kernel, e: Event) -> None:
    if FAN_FLOWS_SEPARATED in k.flags:
        e.status = "blocked"
        k.trace.append(
            TraceEntry(
                event_id=e.id,
                kind=e.kind,
                time=e.time,
                action="blocked",
                cause=list(e.cause),
                blocked_reason="condition_not_met:fan_flows_separated",
            )
        )
        return

    threshold = k.prior("opposing_fans_contact", "colocation_threshold_crowd", 0.5)
    crowd_ok = k.state["crowd_density"] >= threshold
    rumor_ok = RUMOR_SPIKE in k.flags

    if not (crowd_ok or rumor_ok):
        e.status = "blocked"
        k.trace.append(
            TraceEntry(
                event_id=e.id,
                kind=e.kind,
                time=e.time,
                action="blocked",
                cause=list(e.cause),
                blocked_reason="condition_not_met:crowd_density_and_rumor_spike",
            )
        )
        return

    k.set_flag(OPPOSING_FANS_COLOCATED, e)
    delay = int(k.prior("opposing_fans_contact", "emit_conflict_delay", 5))

    k.emit(
        "verbal_conflict",
        payload=e.payload,
        delay=delay,
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="verbal_conflict",
    reads=["verbal_conflict_risk", "scuffle_risk"],
    writes=["verbal_conflict_risk", "scuffle_risk"],
    waits=[OPPOSING_FANS_COLOCATED],
    version="v0.1",
)
def verbal_conflict(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    verbal_delta = k.prior("verbal_conflict", "verbal_risk_delta", 0.25)
    scuffle_delta = k.prior("verbal_conflict", "scuffle_risk_delta", 0.15)

    k.commit(
        e,
        {
            "verbal_conflict_risk": verbal_delta * severity,
            "scuffle_risk": scuffle_delta * severity,
        },
    )


@mechanism(
    kind="fans_gather",
    reads=["crowd_density", "fan_zone_pressure"],
    writes=["crowd_density", "fan_zone_pressure"],
    emits=["bar_district_pressure", "transit_delay"],
    version="v0.1",
)
def fans_gather(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    density_delta = k.prior("fans_gather", "density_delta", 0.15)
    pressure_delta = k.prior("fans_gather", "pressure_delta", 0.12)
    source = e.payload.get("source", "unknown")

    k.commit(
        e,
        {
            "crowd_density": density_delta * severity,
            "fan_zone_pressure": pressure_delta * severity,
        },
    )

    if k.state["crowd_density"] >= k.prior("fans_gather", "high_density_threshold", 0.6):
        k.set_flag(CROWD_DENSITY_HIGH, e)

    bar_delay = int(k.prior("fans_gather", "emit_bar_pressure_delay", 5))
    k.emit(
        "bar_district_pressure",
        payload={"severity": severity},
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + bar_delay,
    )

    if source == "match_end" and k.state["transit_pressure"] >= 0.5:
        k.emit(
            "transit_delay",
            payload={"severity": severity},
            priority=2,
            cause=[f"event:{e.id}"],
            at_time=e.time + 2,
        )

    if TEAM_ELIMINATED in k.flags:
        contact_delay = int(k.prior("fans_gather", "emit_contact_delay", 8))
        k.emit(
            "opposing_fans_contact",
            payload={"severity": severity},
            priority=3,
            cause=[f"event:{e.id}"],
            at_time=e.time + contact_delay,
        )


@mechanism(
    kind="bar_district_pressure",
    reads=["crowd_density", "scuffle_risk"],
    writes=["scuffle_risk", "fan_zone_pressure"],
    emits=["opposing_fans_contact"],
    version="v0.1",
)
def bar_district_pressure(k: Kernel, e: Event) -> None:
    threshold = k.prior("bar_district_pressure", "density_threshold", 0.55)
    if k.state["crowd_density"] < threshold:
        e.status = "blocked"
        k.trace.append(
            TraceEntry(
                event_id=e.id,
                kind=e.kind,
                time=e.time,
                action="blocked",
                cause=list(e.cause),
                blocked_reason="condition_not_met:crowd_density_below_threshold",
            )
        )
        return

    severity = float(e.payload.get("severity", 0.8))
    scuffle_delta = k.prior("bar_district_pressure", "scuffle_delta", 0.12)
    k.commit(e, {"scuffle_risk": scuffle_delta * severity, "fan_zone_pressure": 0.08 * severity})

    k.emit(
        "opposing_fans_contact",
        payload={"severity": severity},
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + int(k.prior("bar_district_pressure", "emit_contact_delay", 6)),
    )


@mechanism(
    kind="crowd_density_spike",
    reads=["crowd_density", "fan_zone_pressure"],
    writes=["crowd_density", "fan_zone_pressure"],
    waits=[TRANSIT_DELAY_ACTIVE],
    emits=["queue_overflow"],
    version="v0.1",
)
def crowd_density_spike(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    density_delta = k.prior("crowd_density_spike", "density_delta", 0.2)
    k.commit(
        e,
        {
            "crowd_density": density_delta * severity,
            "fan_zone_pressure": 0.15 * severity,
        },
    )
    k.set_flag(CROWD_DENSITY_HIGH, e)

    k.emit(
        "queue_overflow",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + int(k.prior("crowd_density_spike", "emit_overflow_delay", 4)),
    )


@mechanism(
    kind="queue_overflow",
    reads=["fan_zone_pressure", "crowd_density"],
    writes=["fan_zone_pressure"],
    waits=[CROWD_DENSITY_HIGH],
    emits=["crowd_push"],
    version="v0.1",
)
def queue_overflow(k: Kernel, e: Event) -> None:
    capacity = k.resources.get("fan_zone_capacity", 800)
    pressure_threshold = k.prior("queue_overflow", "pressure_threshold", 0.65)
    if k.state["fan_zone_pressure"] < pressure_threshold:
        e.status = "blocked"
        k.trace.append(
            TraceEntry(
                event_id=e.id,
                kind=e.kind,
                time=e.time,
                action="blocked",
                cause=list(e.cause),
                blocked_reason="condition_not_met:fan_zone_pressure_below_threshold",
            )
        )
        return

    severity = float(e.payload.get("severity", 0.7))
    k.commit(e, {"fan_zone_pressure": 0.1 * severity})
    _ = capacity  # reserved for future capacity model

    k.emit(
        "crowd_push",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + int(k.prior("queue_overflow", "emit_push_delay", 3)),
    )


@mechanism(
    kind="crowd_push",
    reads=["panic_risk", "crowd_density"],
    writes=["panic_risk"],
    emits=["panic_signal"],
    version="v0.1",
)
def crowd_push(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    panic_delta = k.prior("crowd_push", "panic_delta", 0.25)
    k.commit(e, {"panic_risk": panic_delta * severity})

    k.emit(
        "panic_signal",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + int(k.prior("crowd_push", "emit_signal_delay", 2)),
    )


@mechanism(
    kind="panic_signal",
    reads=["panic_risk"],
    writes=["panic_risk", "riot_risk"],
    version="v0.1",
)
def panic_signal(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    panic_delta = k.prior("panic_signal", "panic_delta", 0.35)
    riot_delta = k.prior("panic_signal", "riot_delta", 0.1)
    k.commit(
        e,
        {
            "panic_risk": panic_delta * severity,
            "riot_risk": riot_delta * severity,
        },
    )
