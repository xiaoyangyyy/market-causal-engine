"""City infrastructure mechanisms: transit, heat, fan zones."""

from __future__ import annotations

from worldcup_causal_engine.constants import (
    CROWD_DENSITY_HIGH,
    HEAT_STRESS_HIGH,
    TRANSIT_DELAY_ACTIVE,
)
from worldcup_causal_engine.kernel import Event, Kernel, TraceEntry
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="transit_delay",
    reads=["transit_pressure", "crowd_density"],
    writes=["transit_pressure"],
    emits=["crowd_density_spike"],
    version="v0.1",
)
def transit_delay(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.7))
    threshold = k.prior("transit_delay", "pressure_threshold", 0.5)
    pressure_delta = k.prior("transit_delay", "pressure_delta", 0.25)

    if k.state["transit_pressure"] < threshold and severity < 0.8:
        e.status = "blocked"
        k.trace.append(
            TraceEntry(
                event_id=e.id,
                kind=e.kind,
                time=e.time,
                action="blocked",
                cause=list(e.cause),
                blocked_reason="condition_not_met:transit_pressure_below_threshold",
            )
        )
        return

    k.commit(e, {"transit_pressure": pressure_delta * severity})
    k.set_flag(TRANSIT_DELAY_ACTIVE, e)

    delay = int(k.prior("transit_delay", "emit_density_spike_delay", 3))
    k.emit(
        "crowd_density_spike",
        payload={"severity": severity},
        priority=1,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )


@mechanism(
    kind="heat_stress_check",
    reads=["heat_stress"],
    writes=["heat_stress", "fan_zone_pressure"],
    version="v0.1",
)
def heat_stress_check(k: Kernel, e: Event) -> None:
    threshold = k.prior("heat_stress_check", "threshold", 0.7)
    if k.state["heat_stress"] >= threshold:
        k.set_flag(HEAT_STRESS_HIGH, e)
        k.commit(e, {"fan_zone_pressure": 0.1})
