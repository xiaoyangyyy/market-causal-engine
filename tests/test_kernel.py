"""Kernel unit tests."""

from __future__ import annotations

import json

from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.registry import register_all_mechanisms


def test_emit_priority_ordering():
    register_all_mechanisms()
    k = Kernel(resources={"official_comm_channel": 5})
    k.state["rumor_volume"] = 0.5

    k.emit("controversial_call", at_time=10, priority=5)
    k.do("official_clarification", at_time=10, payload={"credibility": 0.7})

    k.run(until=10)
    kinds = [e.kind for e in k.trace if e.action == "executed"]
    assert kinds[0] == "official_clarification"


def test_acquire_failure_blocks_without_commit():
    register_all_mechanisms()
    k = Kernel(resources={"official_comm_channel": 0}, priors={})
    k.state["rumor_volume"] = 0.8

    event = k.do("official_clarification", at_time=1, payload={"credibility": 0.7})
    k.run(until=1)

    assert event.status == "blocked"
    assert k.state["rumor_volume"] == 0.8
    blocked = [e for e in k.trace if e.action == "blocked"]
    assert any("resource_shortage" in (e.blocked_reason or "") for e in blocked)


def test_flag_trace():
    register_all_mechanisms()
    k = Kernel(priors={
        "controversial_call": {"unfairness_delta": 0.35, "tension_delta": 0.25, "emit_viral_clip_delay": 0},
        "viral_clip_published": {"platform_velocity_delta": 0.3, "emit_blame_frame_delay": 99},
        "media_blame_frame": {"outrage_delta": 0.3, "blame_delta": 0.2, "emit_rumor_delay": 99},
    })
    k.emit("controversial_call", at_time=1, payload={"severity": 0.8})
    k.run(until=1)

    flag_actions = [e for e in k.trace if e.action == "set_flag"]
    assert any("CONTROVERSIAL_CALL_VISIBLE" in e.flags_delta for e in flag_actions)


def test_reproducibility():
    from worldcup_causal_engine.scenarios import run_scenario
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    scenario = root / "data" / "scenarios" / "S1_controversial_call_high_density.json"

    r1 = run_scenario(scenario, world_id="W0", until=120)
    r2 = run_scenario(scenario, world_id="W0", until=120)

    assert r1["final_risk"] == r2["final_risk"]
    assert r1["dominant_path"] == r2["dominant_path"]
