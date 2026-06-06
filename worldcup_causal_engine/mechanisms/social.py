"""Social propagation mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import MEDIA_OUTRAGE_FRAME_ACTIVE, RUMOR_SPIKE
from worldcup_causal_engine.kernel import Event, Kernel
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="rumor_amplified",
    reads=["rumor_volume", "misinfo_confidence", "platform_velocity"],
    writes=["rumor_volume", "misinfo_confidence", "platform_velocity"],
    waits=[MEDIA_OUTRAGE_FRAME_ACTIVE],
    resources=["media_attention_budget"],
    emits=["offline_mood_shift"],
    version="v0.1",
)
def rumor_amplified(k: Kernel, e: Event) -> None:
    if not k.acquire("media_attention_budget", 2, e):
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.8))
    rumor_delta = k.prior("rumor_amplified", "rumor_delta", 0.35)
    misinfo_delta = k.prior("rumor_amplified", "misinfo_delta", 0.2)
    threshold = k.prior("rumor_amplified", "rumor_spike_threshold", 0.6)
    delay = int(k.prior("rumor_amplified", "emit_mood_shift_delay", 5))

    k.commit(
        e,
        {
            "rumor_volume": rumor_delta * severity,
            "misinfo_confidence": misinfo_delta * severity,
            "platform_velocity": 0.1 * severity,
        },
    )

    if k.state["rumor_volume"] >= threshold:
        k.set_flag(RUMOR_SPIKE, e)

    k.emit(
        "offline_mood_shift",
        payload={"severity": severity},
        delay=delay,
        priority=3,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )
