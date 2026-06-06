"""Phase 4: ablation, sensitivity, scoring, LLM baseline tests."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.config import KernelConfig
from worldcup_causal_engine.experiments.ablation import run_ablation
from worldcup_causal_engine.experiments.metrics import compute_ablation_metrics
from worldcup_causal_engine.experiments.scoring import compare_explainability, score_kernel
from worldcup_causal_engine.experiments.sensitivity import run_sensitivity_grid
from worldcup_causal_engine.experiments.llm_baseline import mock_llm_response, run_llm_baseline
from worldcup_causal_engine.scenarios import load_scenario, run_scenario

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"


def test_kernel_config_ablation_flags():
    a1 = KernelConfig.ablation("A1")
    assert a1.use_flags is False
    a4 = KernelConfig.ablation("A4")
    assert a4.use_trace is False


def test_ablation_a4_no_trace():
    result = run_scenario(S1, world_id="W0", kernel_config=KernelConfig.ablation("A4"))
    assert result.get("trace") == []
    metrics = compute_ablation_metrics(result)
    assert metrics["has_trace"] is False


def test_ablation_a2_no_resource_block_on_s3():
    s3 = ROOT / "data" / "scenarios" / "S3_heat_crowd_comm_delay.json"
    full = run_scenario(s3, world_id="W1")
    ablated = run_scenario(s3, world_id="W1", kernel_config=KernelConfig.ablation("A2"))
    full_blocked = sum(1 for e in full.get("trace", []) if e.get("action") == "blocked")
    abl_blocked = sum(1 for e in ablated.get("trace", []) if e.get("action") == "blocked")
    assert abl_blocked <= full_blocked


def test_run_ablation_mini(tmp_path):
    summary = run_ablation(scenarios=["S1"], ablation_ids=["full", "A1", "A4"], output_dir=tmp_path)
    assert summary["runs"] >= 3
    assert (tmp_path / "ablation_summary.json").exists()


def test_sensitivity_runs(tmp_path):
    summary = run_sensitivity_grid(scenario="S1", output_dir=tmp_path, max_runs=20)
    assert summary["runs"] > 0
    assert "verbal_conflict_range" in summary


def test_mock_llm_and_scoring():
    scenario = load_scenario(S1)
    w0 = mock_llm_response(scenario, "W0", [], {}, run_id=0)
    w1 = mock_llm_response(scenario, "W1", [], {}, run_id=1)
    assert w0["dominant_path"]
    kernel_w0 = run_scenario(S1, world_id="W0")
    kernel_w1 = run_scenario(S1, world_id="W1")
    scores = compare_explainability(
        kernel_w0, kernel_w1, [w0], [w1], scenario.get("resources")
    )
    assert scores["kernel"]["traceability"] == 1.0
    assert "llm" in scores


def test_run_llm_baseline(tmp_path):
    scores = run_llm_baseline("S1", worlds=["W0", "W1"], runs=2, output_dir=tmp_path)
    assert (tmp_path / "explainability_scores.json").exists()
    assert scores["kernel"]["consistency"] == 1.0


def test_score_kernel_intervention_diff():
    w0 = run_scenario(S1, world_id="W0")
    w1 = run_scenario(S1, world_id="W1")
    s = score_kernel(w1, w0)
    assert s["intervention_diff"] == 1.0
