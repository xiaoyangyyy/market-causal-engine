"""Priority C: LLM API proposer, MDG viz, S4-S6, W6."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.constants import SCENARIO_FILES
from worldcup_causal_engine.mdg.builder import build_event_mdg_from_result
from worldcup_causal_engine.mdg.export import export_mermaid
from worldcup_causal_engine.scenarios import run_llm_propose_demo, run_scenario

ROOT = Path(__file__).resolve().parent.parent
S4 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S4"]
S5 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S5"]
S6 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S6"]
S3 = ROOT / "data" / "scenarios" / SCENARIO_FILES["S3"]


def test_s4_misleading_viral_runs():
    r = run_scenario(S4, world_id="W0", until=120)
    assert "viral_clip_published" in r["dominant_path"]
    assert r["final_state"]["misinfo_confidence"] > 0.2


def test_s5_transit_panic_chain():
    r = run_scenario(S5, world_id="W0", until=120)
    path = r["dominant_path"]
    assert "transit_delay" in path or "match_end" in path
    assert r["final_risk"]["panic"] >= 0 or r["final_risk"]["verbal_conflict"] >= 0


def test_s6_heat_fanzone_runs():
    r = run_scenario(S6, world_id="W0", until=120)
    assert r["final_state"]["heat_stress"] >= 0.9
    assert "match_end" in r["dominant_path"] or "fans_gather" in r["dominant_path"]


def test_w6_platform_throttle_reduces_s4_rumor():
    w0 = run_scenario(S4, world_id="W0", until=120)
    w6 = run_scenario(S4, world_id="W6", until=120)
    assert w6["final_state"]["rumor_volume"] <= w0["final_state"]["rumor_volume"]


def test_mdg_mermaid_export():
    r = run_scenario(S5, world_id="W0", until=120)
    mdg = build_event_mdg_from_result(r)
    mmd = export_mermaid(mdg, title="S5")
    assert "flowchart" in mmd
    assert "-->" in mmd


def test_llm_propose_demo_mock():
    r = run_llm_propose_demo(S3, use_api=False, mock_kind="official_clarification", mock_time=87)
    assert "proposal_verification" in r
    assert r["proposal_verification"]["accepted"]
    assert r["llm_proposal"]["kind"] == "transit_reroute"
    assert r["intervention_effect"]["improved"]


def test_all_six_scenarios_in_registry():
    assert len(SCENARIO_FILES) == 6
