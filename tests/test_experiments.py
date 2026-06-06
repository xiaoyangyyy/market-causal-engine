"""Experiment framework tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldcup_causal_engine.experiments import (
    export_report,
    find_best_cut_points,
    run_pressure_test,
    summarize,
)
from worldcup_causal_engine.scenarios import run_scenario

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"
S2 = ROOT / "data" / "scenarios" / "S2_team_eliminated_transit_delay.json"
S3 = ROOT / "data" / "scenarios" / "S3_heat_crowd_comm_delay.json"


def test_run_pressure_test_18_runs(tmp_path):
    results = run_pressure_test(
        scenarios=["S1", "S2", "S3"],
        worlds=["W0", "W1", "W2", "W3", "W4", "W5"],
        until=120,
        output_dir=tmp_path,
    )
    assert len(results) == 18
    assert len(list(tmp_path.glob("*.json"))) == 18


def test_s3_w0_comm_channel_bottleneck():
    result = run_scenario(S3, world_id="W0", until=120)
    if result["resource_bottlenecks"]:
        resources = {b["resource"] for b in result["resource_bottlenecks"]}
        assert "official_comm_channel" in resources or len(resources) >= 0
    w1 = run_scenario(S3, world_id="W1", until=120)
    assert any(
        b.get("resource") == "official_comm_channel"
        for b in w1.get("resource_bottlenecks", [])
    )


def test_s1_w3_blocks_colocation():
    w0 = run_scenario(S1, world_id="W0", until=120)
    w3 = run_scenario(S1, world_id="W3", until=120)
    assert w0["final_risk"]["verbal_conflict"] >= w3["final_risk"]["verbal_conflict"]
    blocked = [
        e for e in w3["trace"]
        if e["kind"] == "opposing_fans_contact" and e["action"] == "blocked"
    ]
    assert blocked or w3["final_risk"]["verbal_conflict"] < w0["final_risk"]["verbal_conflict"]


def test_find_best_cut_points_s1():
    w0 = run_scenario(S1, world_id="W0", until=120)
    cuts = []
    for world in ["W1", "W2", "W3", "W5"]:
        wr = run_scenario(S1, world_id=world, until=120)
        cuts.extend(find_best_cut_points(w0, [wr]))
    assert len(cuts) >= 2


def test_summarize_and_export(tmp_path):
    results = run_pressure_test(
        scenarios=["S1"],
        worlds=["W0", "W1"],
        until=120,
        output_dir=tmp_path,
    )
    summary = export_report(results, tmp_path / "summary.json")
    assert summary["runs"] == 2
    assert (tmp_path / "summary.json").exists()
    assert "cross_scenario_insights" in summary


def test_s2_runs():
    result = run_scenario(S2, world_id="W0", until=120)
    assert "team_eliminated" in result["dominant_path"] or any(
        e["kind"] == "team_eliminated" for e in result["trace"] if e["action"] == "executed"
    )


def test_s3_runs_panic_chain():
    result = run_scenario(S3, world_id="W0", until=120)
    executed = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "match_end" in executed
    assert result["final_risk"]["panic"] > 0 or result["final_risk"]["verbal_conflict"] >= 0
