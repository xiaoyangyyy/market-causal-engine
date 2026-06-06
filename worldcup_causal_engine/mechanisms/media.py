"""Media and outrage-frame mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import (
    CONTROVERSIAL_CALL_VISIBLE,
    MEDIA_OUTRAGE_FRAME_ACTIVE,
)
from worldcup_causal_engine.kernel import Event, Kernel
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="viral_clip_published",
    reads=["platform_velocity", "media_attention"],
    writes=["platform_velocity", "media_attention"],
    waits=[CONTROVERSIAL_CALL_VISIBLE],
    resources=["media_attention_budget"],
    emits=["media_blame_frame"],
    version="v0.1",
)
def viral_clip_published(k: Kernel, e: Event) -> None:
    if not k.acquire("media_attention_budget", 1, e):
        e.status = "blocked"
        return

    severity = float(e.payload.get("severity", 0.8))
    velocity_delta = k.prior("viral_clip_published", "platform_velocity_delta", 0.3)

    k.commit(
        e,
        {
            "platform_velocity": velocity_delta * severity,
            "media_attention": 0.1 * severity,
        },
    )

    blame_delay = int(k.prior("viral_clip_published", "emit_blame_frame_delay", 5))
    k.emit(
        "media_blame_frame",
        payload={"severity": severity},
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + blame_delay,
    )


@mechanism(
    kind="media_blame_frame",
    reads=["outrage_frame", "blame_frame"],
    writes=["outrage_frame", "blame_frame"],
    waits=[CONTROVERSIAL_CALL_VISIBLE],
    emits=["rumor_amplified"],
    version="v0.1",
)
def media_blame_frame(k: Kernel, e: Event) -> None:
    severity = float(e.payload.get("severity", 0.8))
    outrage_delta = k.prior("media_blame_frame", "outrage_delta", 0.3)
    blame_delta = k.prior("media_blame_frame", "blame_delta", 0.2)
    delay = int(k.prior("media_blame_frame", "emit_rumor_delay", 8))

    k.commit(
        e,
        {
            "outrage_frame": outrage_delta * severity,
            "blame_frame": blame_delta * severity,
        },
    )
    k.set_flag(MEDIA_OUTRAGE_FRAME_ACTIVE, e)

    k.emit(
        "rumor_amplified",
        payload={"severity": severity},
        delay=delay,
        priority=2,
        cause=[f"event:{e.id}"],
        at_time=e.time + delay,
    )
