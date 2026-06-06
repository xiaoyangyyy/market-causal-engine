"""Mechanism and integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from worldcup_causal_engine.constants import (
    CONTROVERSIAL_CALL_VISIBLE,
    MEDIA_OUTRAGE_FRAME_ACTIVE,
    RUMOR_SPIKE,
)
from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.registry import register_all_mechanisms
from worldcup_causal_engine.scenarios import load_priors, run_scenario


ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"


@pytest.fixture
def priors():
    return load_priors()


def test_controversial_call_sets_flag(priors):
    register_all_mechanisms()
    k = Kernel(
        resources={"media_attention_budget": 100},
        priors=priors,
    )
    k.emit("controversial_call", at_time=1, payload={"severity": 0.8})
    k.run(until=1)
    assert CONTROVERSIAL_CALL_VISIBLE in k.flags


def test_rumor_amplified_blocked_without_outrage_flag(priors):
    register_all_mechanisms()
    k = Kernel(resources={"media_attention_budget": 100}, priors=priors)
    k.emit("rumor_amplified", at_time=1, payload={"severity": 0.8})
    k.run(until=1)

    blocked = [e for e in k.trace if e.kind == "rumor_amplified" and e.action == "blocked"]
    assert blocked
    assert MEDIA_OUTRAGE_FRAME_ACTIVE not in k.flags


def test_official_clarification_zero_resource(priors):
    register_all_mechanisms()
    k = Kernel(
        resources={"official_comm_channel": 0, "media_attention_budget": 100},
        priors=priors,
    )
    k.state["rumor_volume"] = 0.7
    k.flags.add(RUMOR_SPIKE)
    k.do("official_clarification", at_time=50, payload={"credibility": 0.7})
    k.run(until=50)

    assert k.state["rumor_volume"] == 0.7
    assert RUMOR_SPIKE in k.flags


def test_s1_w0_full_chain():
    result = run_scenario(S1, world_id="W0", until=120)

    assert result["final_risk"]["verbal_conflict"] > 0.5
    path = result["dominant_path"]
    for node in [
        "controversial_call",
        "media_blame_frame",
        "rumor_amplified",
        "opposing_fans_contact",
        "verbal_conflict",
    ]:
        assert node in path


def test_s1_w1_reduces_risk():
    w0 = run_scenario(S1, world_id="W0", until=120)
    w1 = run_scenario(S1, world_id="W1", until=120)

    assert w1["final_risk"]["verbal_conflict"] < w0["final_risk"]["verbal_conflict"]
    assert RUMOR_SPIKE not in w1["active_flags"] or w0["final_risk"]["verbal_conflict"] > w1["final_risk"]["verbal_conflict"]


def test_s1_w1_blocked_when_no_comm_channel():
    import json
    import tempfile

    with open(S1, encoding="utf-8") as f:
        scenario = json.load(f)
    scenario["resources"]["official_comm_channel"] = 0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(scenario, tmp)
        tmp_path = tmp.name

    w0 = run_scenario(S1, world_id="W0", until=120)
    w1_blocked = run_scenario(tmp_path, world_id="W1", until=120)

    assert any(b["resource"] == "official_comm_channel" for b in w1_blocked["resource_bottlenecks"])
    assert abs(w1_blocked["final_risk"]["verbal_conflict"] - w0["final_risk"]["verbal_conflict"]) < 0.05
