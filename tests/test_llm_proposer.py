"""LLM proposer: verify-at-time, context, multi-round retries."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.constants import SCENARIO_FILES
from worldcup_causal_engine.ir.proposal import Proposal
from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.proposers.context import (
    build_event_schedule,
    clear_context_cache,
    compute_intervention_timing,
    gather_intervention_context,
    proposal_checkpoint,
)
from worldcup_causal_engine.proposers.llm import LLMProposer, normalize_proposal_timing
from worldcup_causal_engine.registry import register_all_mechanisms
from worldcup_causal_engine.scenarios import (
    build_kernel,
    inject_trigger,
    load_scenario,
    run_llm_propose_demo,
    run_scenario,
)

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S1"]
S3 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S3"]
S4 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S4"]
S5 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S5"]


def _kernel_at_s1_checkpoint():
    register_all_mechanisms()
    scenario = load_scenario(S1)
    kernel = build_kernel(scenario, world_id="W0")
    inject_trigger(kernel, scenario["trigger"])
    kernel.run(until=proposal_checkpoint(scenario))
    return kernel, scenario


def test_verify_at_proposal_time_accepts_s1_at_88():
    """Clarification at t=88 passes pre-check (rumor_volume>0 at t=87)."""
    kernel, _ = _kernel_at_s1_checkpoint()
    proposal = Proposal(
        id="P-test",
        kind="official_clarification",
        time=88,
        payload={"topic": "controversial_call", "credibility": 0.8},
        proposer="test",
        priority=0,
    )
    vr = kernel.propose(proposal)
    assert vr.accepted, vr.detail


def test_verify_at_proposal_time_rejects_s1_at_72():
    """Early clarification fails pre at t=71 (rumor not yet active)."""
    kernel, _ = _kernel_at_s1_checkpoint()
    proposal = Proposal(
        id="P-early",
        kind="official_clarification",
        time=72,
        payload={"credibility": 0.7},
        proposer="test",
    )
    vr = kernel.propose(proposal)
    assert not vr.accepted
    assert vr.reason_code == "pre_condition"


def test_gather_context_includes_cut_points_and_hints():
    clear_context_cache()
    ctx = gather_intervention_context(S4, until=120, use_cache=False)
    assert ctx["baseline_w0"]["dominant_path"]
    assert "platform_rumor_throttle" in ctx.get("recommended_interventions", []) or any(
        "platform" in str(cp.get("intervention", "")) for cp in ctx.get("best_cut_points", [])
    )
    assert any("misinfo" in h.lower() or "platform" in h.lower() for h in ctx.get("scenario_hints", []))


def test_s1_mock_retry_accepts_and_reduces_verbal():
    clear_context_cache()
    r = run_llm_propose_demo(
        S1,
        use_api=False,
        mock_kind="official_clarification",
        mock_time=72,
        max_attempts=3,
    )
    assert r["proposal_verification"]["accepted"]
    assert len(r["proposal_attempts"]) >= 2
    assert r["final_risk"]["verbal_conflict"] < 0.52
    assert r["intervention_effect"]["improved"]


def test_s3_mock_retry_picks_transit_not_clarify():
    clear_context_cache()
    r = run_llm_propose_demo(
        S3,
        use_api=False,
        mock_kind="official_clarification",
        mock_time=87,
        max_attempts=3,
    )
    assert r["proposal_verification"]["accepted"]
    assert r["llm_proposal"]["kind"] == "transit_reroute"
    assert r["final_risk"]["panic"] == 0.0
    assert r["intervention_effect"]["improved"]


def test_s4_mock_retry_platform_throttle():
    clear_context_cache()
    w0 = run_scenario(S4, world_id="W0", until=120)
    r = run_llm_propose_demo(
        S4,
        use_api=False,
        mock_kind="official_clarification",
        mock_time=62,
        max_attempts=3,
    )
    assert r["proposal_verification"]["accepted"]
    assert r["llm_proposal"]["kind"] == "platform_rumor_throttle"
    assert r["final_risk"]["verbal_conflict"] < w0["final_risk"]["verbal_conflict"]
    assert r["intervention_effect"]["improved"]


def test_s5_context_transit_reroute_timing():
    clear_context_cache()
    ctx = gather_intervention_context(S5, use_cache=False)
    assert ctx["event_schedule"]["transit_delay"] == 93
    assert ctx["intervention_timing"]["transit_reroute"] == 96
    assert any("t=93" in h and "t=96" in h for h in ctx["scenario_hints"])


def test_normalize_transit_reroute_bumps_same_minute_as_delay():
    ctx = gather_intervention_context(S5, use_cache=False)
    fixed = normalize_proposal_timing({"kind": "transit_reroute", "time": 93}, ctx)
    assert fixed["time"] == 96
    assert fixed.get("timing_adjusted_from") == 93


def test_s5_transit_reroute_timing_sweep():
    """t=93 ineffective; t=94..96 cut panic (matches W4 @96)."""
    register_all_mechanisms()
    scenario = load_scenario(S5)
    w0 = run_scenario(S5, world_id="W0", until=120)
    baseline_panic = w0["final_risk"]["panic"]
    assert baseline_panic == 1.0

    proposer = LLMProposer("test")
    for t, expect_panic_zero in [(93, False), (94, True), (95, True), (96, True), (97, False)]:
        k = build_kernel(scenario, world_id="W0")
        for tr in scenario["triggers"]:
            inject_trigger(k, tr)
        k.run(until=proposal_checkpoint(scenario))
        vr = proposer.propose_kind(k, "transit_reroute", time=t, payload={"capacity_delta": 200})
        assert vr.accepted
        k.run(until=120)
        panic = k.to_result()["final_risk"]["panic"]
        if expect_panic_zero:
            assert panic == 0.0, f"t={t} expected panic 0 got {panic}"
        else:
            assert panic == 1.0, f"t={t} expected panic 1 got {panic}"


def test_s5_mock_transit_reroute_matches_w4_panic():
    clear_context_cache()
    w4 = run_scenario(S5, world_id="W4", until=120)
    r = run_llm_propose_demo(
        S5,
        use_api=False,
        mock_kind="transit_reroute",
        mock_time=93,
        max_attempts=3,
    )
    assert r["proposal_verification"]["accepted"]
    assert r["llm_proposal"]["kind"] == "transit_reroute"
    assert r["llm_proposal"]["time"] == 96
    assert r["final_risk"]["panic"] == 0.0
    assert r["final_risk"]["panic"] == w4["final_risk"]["panic"]
    assert r["intervention_effect"]["improved"]


def test_s5_schedule_helpers():
    scenario = load_scenario(S5)
    sched = build_event_schedule(scenario)
    timing = compute_intervention_timing(scenario, sched)
    assert sched["match_end"] == 90
    assert sched["transit_delay"] == 93
    assert timing["transit_reroute"] == 96


def test_kernel_clone_preserves_queue():
    register_all_mechanisms()
    k = Kernel(resources={"official_comm_channel": 5})
    k.emit("controversial_call", at_time=60, payload={"severity": 0.8})
    k.run(until=60)
    clone = k.clone()
    assert clone.current_time == k.current_time
    assert clone.state == k.state
