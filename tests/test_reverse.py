"""Reverse debugger tests."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.reverse import ReverseDebugger, analyze_result, diff_results
from worldcup_causal_engine.scenarios import run_scenario

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"


def test_trace_path_returns_chain():
    result = run_scenario(S1, world_id="W0", until=120)
    dbg = analyze_result(result)
    executed_ids = [
        e["event_id"] for e in result["trace"] if e["action"] == "executed"
    ]
    assert executed_ids
    path = dbg.trace_path(executed_ids[-1])
    assert "controversial_call" in path
    assert path[-1] in ("verbal_conflict", "opposing_fans_contact", "rumor_amplified")


def test_why_blocked_resource():
    result = run_scenario(S1, world_id="W1", until=120)
    import json
    import tempfile

    with open(S1, encoding="utf-8") as f:
        scenario = json.load(f)
    scenario["resources_override"] = {"official_comm_channel": 0}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(scenario, tmp)
        tmp_path = tmp.name

    blocked_result = run_scenario(tmp_path, world_id="W1", until=120)
    dbg = analyze_result(blocked_result)
    blocked_entries = [e for e in blocked_result["trace"] if e["action"] == "blocked"
                       and e["kind"] == "official_clarification"]
    assert blocked_entries
    info = dbg.why_blocked(blocked_entries[0]["event_id"])
    assert info["blocked"] is True
    assert "resource_shortage" in info["reason"]


def test_diff_trace_finds_fork():
    w0 = run_scenario(S1, world_id="W0", until=120)
    w1 = run_scenario(S1, world_id="W1", until=120)
    diff = diff_results(w0, w1)
    assert diff["diverged"] is True
    assert diff["fork_point"] is not None
    assert "official_clarification" in diff["only_b"] or "official_clarification" in diff["path_b"]


def test_dominant_risk_path_s1():
    result = run_scenario(S1, world_id="W0", until=120)
    dbg = analyze_result(result)
    path = dbg.dominant_risk_path()
    assert "controversial_call" in path
    assert "verbal_conflict" in path


def test_why_not_happen():
    w1 = run_scenario(S1, world_id="W1", until=120)
    dbg = analyze_result(w1)
    info = dbg.why_not_happen("verbal_conflict")
    assert info["happened"] is False
    assert info["reason"] in ("blocked", "never_scheduled", "never_scheduled_or_missing_prerequisites")


def test_resource_bottlenecks_and_flag_lifecycle():
    result = run_scenario(S1, world_id="W0", until=120)
    dbg = analyze_result(result)
    lifecycle = dbg.flag_lifecycle("RUMOR_SPIKE")
    assert any(action == "set" for _, action in lifecycle)
    history = dbg.variable_history("verbal_conflict_risk")
    assert history
    assert dbg.explain(scenario_id="S1", world_id="W0")
