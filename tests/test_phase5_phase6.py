"""Phase 5 (contracts + verification) and Phase 6 (causal ledger + fork)."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.config import KernelConfig
from worldcup_causal_engine.ir.proposal import Proposal
from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.ledger.fork import diff_branches, replay_fork_from_scenario
from worldcup_causal_engine.proposers.llm import LLMProposer
from worldcup_causal_engine.registry import register_all_mechanisms
from worldcup_causal_engine.scenarios import build_kernel, load_scenario, run_scenario

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"
S3 = ROOT / "data" / "scenarios" / "S3_heat_crowd_comm_delay.json"


def test_proposal_rejected_resource_shortage_s3():
    """LLM proposes official_clarification when channel=0 — kernel rejects."""
    register_all_mechanisms()
    scenario = load_scenario(S3)
    kernel = build_kernel(scenario, world_id="W0")

    for trigger in scenario.get("triggers", []):
        from worldcup_causal_engine.scenarios import inject_trigger

        inject_trigger(kernel, trigger)

    kernel.run(until=86)

    proposer = LLMProposer()
    result = proposer.propose_kind(
        kernel,
        "official_clarification",
        time=87,
        payload={"topic": "controversial_call", "credibility": 0.7},
    )

    assert not result.accepted
    assert result.reason_code == "resource_shortage"

    verifications = [e for e in kernel.trace if e.action == "verification"]
    assert verifications
    assert verifications[-1].verification["accepted"] is False

    blocked = [e for e in kernel.trace if e.action == "blocked" and e.kind == "official_clarification"]
    assert blocked
    assert "resource_shortage" in (blocked[-1].blocked_reason or "")


def test_contract_verification_in_run_trace():
    register_all_mechanisms()
    k = Kernel(resources={"official_comm_channel": 0}, priors={})
    k.state["rumor_volume"] = 0.5
    k.do("official_clarification", at_time=1, payload={"credibility": 0.7})
    k.run(until=1)

    ver = [e for e in k.trace if e.action == "verification"]
    assert ver
    assert ver[0].verification["reason_code"] == "resource_shortage"


def test_no_contract_baseline_still_blocks_in_handler():
    register_all_mechanisms()
    cfg = KernelConfig.full()
    cfg.use_contracts = False
    k = Kernel(resources={"official_comm_channel": 0}, priors={}, config=cfg)
    k.state["rumor_volume"] = 0.8
    k.do("official_clarification", at_time=1, payload={"credibility": 0.7})
    k.run(until=1)

    blocked = [e for e in k.trace if e.action == "blocked"]
    assert any("resource_shortage" in (e.blocked_reason or "") for e in blocked)


def test_causal_ledger_snapshots_on_execute():
    result = run_scenario(S1, world_id="W0", until=120)
    ledger = result.get("causal_ledger")
    assert ledger is not None
    assert len(ledger["snapshots"]) >= 5
    assert ledger["executed_path"] == result["dominant_path"]


def test_fork_equivalent_to_full_w1_s1():
    _baseline, fork_result, full_w1 = replay_fork_from_scenario(
        S1,
        baseline_world="W0",
        fork_before_kind="rumor_amplified",
        intervention_world="W1",
        until=120,
    )

    assert fork_result.equivalence_note == "fork_replay_complete"
    assert fork_result.dominant_path == full_w1["dominant_path"]
    assert fork_result.final_risk == full_w1["final_risk"]


def test_diff_branches_w0_vs_w1():
    w0 = run_scenario(S1, world_id="W0", until=120)
    w1 = run_scenario(S1, world_id="W1", until=120)
    diff = diff_branches(w0["dominant_path"], w1["dominant_path"])

    assert diff["diverged"]
    assert "official_clarification" in diff["only_b"] or "rumor_amplified" in diff["only_a"]


def test_accepted_proposal_enqueues_event():
    register_all_mechanisms()
    k = Kernel(resources={"official_comm_channel": 5}, priors={})
    k.state["rumor_volume"] = 0.6
    k.set_flag("RUMOR_SPIKE", k.emit("dummy", at_time=0))

    proposal = Proposal(
        id="P-test-1",
        kind="official_clarification",
        time=10,
        payload={"credibility": 0.8},
        proposer="llm",
        priority=0,
    )
    vr = k.propose(proposal)
    assert vr.accepted
    k.run(until=10)
    executed = [e.kind for e in k.trace if e.action == "executed"]
    assert "official_clarification" in executed
