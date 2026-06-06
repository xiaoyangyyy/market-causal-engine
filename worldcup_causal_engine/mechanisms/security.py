"""Security and governance mechanisms."""

from __future__ import annotations

from worldcup_causal_engine.constants import POLICE_TRUST_LOW
from worldcup_causal_engine.kernel import Event, Kernel
from worldcup_causal_engine.registry import mechanism


@mechanism(
    kind="police_trust_check",
    reads=["police_trust", "police_visibility"],
    writes=[],
    version="v0.1",
)
def police_trust_check(k: Kernel, e: Event) -> None:
    threshold = k.prior("police_trust_check", "low_threshold", 0.45)
    if k.state["police_trust"] < threshold:
        k.set_flag(POLICE_TRUST_LOW, e)
