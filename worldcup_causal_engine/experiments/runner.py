"""Batch experiments: pressure test, summarization, cut-point analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldcup_causal_engine.constants import SCENARIO_FILES, WORLD_IDS
from worldcup_causal_engine.reverse import analyze_result, diff_results
from worldcup_causal_engine.scenarios import _project_root, run_scenario


@dataclass
class RunResult:
    scenario_id: str
    world_id: str
    result: dict[str, Any] = field(default_factory=dict)


def resolve_scenario_path(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.exists():
        return path
    short = name_or_path.upper()
    if short in SCENARIO_FILES:
        return _project_root() / "data" / "scenarios" / SCENARIO_FILES[short]
    raise FileNotFoundError(f"Scenario not found: {name_or_path}")


def run_pressure_test(
    scenarios: list[str],
    worlds: list[str] | None = None,
    until: int = 120,
    output_dir: str | Path | None = None,
) -> list[RunResult]:
    worlds = worlds or WORLD_IDS
    results: list[RunResult] = []
    out_root = Path(output_dir) if output_dir else _project_root() / "results" / "experiment_1"
    out_root.mkdir(parents=True, exist_ok=True)

    for scenario_name in scenarios:
        scenario_path = resolve_scenario_path(scenario_name)
        for world_id in worlds:
            result = run_scenario(scenario_path, world_id=world_id, until=until)
            run = RunResult(
                scenario_id=result["scenario_id"],
                world_id=world_id,
                result=result,
            )
            results.append(run)
            fname = f"{result['scenario_id']}_{world_id}.json"
            (out_root / fname).write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    return results


def find_best_cut_points(
    base_run: dict[str, Any],
    intervention_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cut_points: list[dict[str, Any]] = []
    base_path = base_run.get("dominant_path", [])
    base_verbal = base_run.get("final_risk", {}).get("verbal_conflict", 0.0)
    base_panic = base_run.get("final_risk", {}).get("panic", 0.0)
    intervention_kind_map = {
        "W1": "official_clarification",
        "W2": "team_captain_message",
        "W3": "separate_fan_flows",
        "W4": "transit_reroute",
        "W5": "deploy_deescalation",
        "W6": "platform_rumor_throttle",
    }
    for irun in intervention_runs:
        world_id = irun.get("world_id", "")
        if world_id == "W0":
            continue
        diff = diff_results(base_run, irun)
        intervention_kind = intervention_kind_map.get(world_id, world_id)
        before = diff.get("fork_point") or (base_path[-1] if base_path else "unknown")
        if diff.get("only_b"):
            before = diff["only_b"][0] if len(diff["only_b"]) > 1 else before
        verbal = irun.get("final_risk", {}).get("verbal_conflict", 0.0)
        panic = irun.get("final_risk", {}).get("panic", 0.0)
        risk_reduction = max(base_verbal - verbal, base_panic - panic, 0.0)
        if diff.get("diverged") or risk_reduction > 0:
            cut_points.append({
                "intervention": intervention_kind,
                "before": before,
                "world_id": world_id,
                "risk_reduction": round(risk_reduction, 4),
                "fork_point": diff.get("fork_point"),
            })
    cut_points.sort(key=lambda x: -x["risk_reduction"])
    return cut_points


def summarize(results: list[RunResult]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    bottleneck_counts: dict[str, int] = {}
    intervention_scores: dict[str, float] = {}
    grouped: dict[str, list[RunResult]] = {}
    for run in results:
        grouped.setdefault(run.scenario_id, []).append(run)

    for scenario_id, runs in grouped.items():
        base = next((r for r in runs if r.world_id == "W0"), None)
        base_result = base.result if base else {}
        for run in runs:
            result = run.result
            dbg = analyze_result(result)
            row = {
                "scenario_id": scenario_id,
                "world_id": run.world_id,
                "final_risk": result.get("final_risk", {}),
                "dominant_path": dbg.dominant_risk_path(),
                "resource_bottlenecks": dbg.resource_bottlenecks(),
                "best_cut_points": [],
            }
            if base_result and run.world_id != "W0":
                row["best_cut_points"] = find_best_cut_points(base_result, [result])
            rows.append(row)
            for bn in dbg.resource_bottlenecks():
                bottleneck_counts[bn["resource"]] = (
                    bottleneck_counts.get(bn["resource"], 0) + bn["failures"]
                )
            if base_result and run.world_id != "W0":
                base_v = base_result.get("final_risk", {}).get("verbal_conflict", 0.0)
                run_v = result.get("final_risk", {}).get("verbal_conflict", 0.0)
                base_p = base_result.get("final_risk", {}).get("panic", 0.0)
                run_p = result.get("final_risk", {}).get("panic", 0.0)
                score = max(base_v - run_v, base_p - run_p, 0.0)
                intervention_scores[run.world_id] = (
                    intervention_scores.get(run.world_id, 0.0) + score
                )

    most_effective = max(intervention_scores, key=intervention_scores.get) if intervention_scores else None
    most_bottleneck = max(bottleneck_counts, key=bottleneck_counts.get) if bottleneck_counts else None
    return {
        "experiment": "pressure_test",
        "runs": len(results),
        "results": rows,
        "cross_scenario_insights": {
            "most_effective_intervention": most_effective,
            "most_common_bottleneck": most_bottleneck,
            "intervention_scores": intervention_scores,
        },
    }


def export_report(results: list[RunResult], path: str | Path) -> dict[str, Any]:
    summary = summarize(results)
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
