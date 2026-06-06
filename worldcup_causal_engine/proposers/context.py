"""Intervention hints for LLM proposer: baseline path, cut points, bottlenecks."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from worldcup_causal_engine.experiments.runner import find_best_cut_points
from worldcup_causal_engine.reverse import analyze_result
from worldcup_causal_engine.scenarios import load_scenario, run_scenario

_INTERVENTION_WORLDS = ("W1", "W3", "W4", "W5", "W6")


def proposal_checkpoint(scenario: dict[str, Any]) -> int:
    """Earliest match minute to pause before LLM proposes (after first trigger fires)."""
    times: list[int] = []
    trigger = scenario.get("trigger")
    if trigger:
        times.append(int(trigger.get("time", 55)))
    for item in scenario.get("triggers", []):
        times.append(int(item.get("time", 55)))
    return min(times) if times else 55


def build_event_schedule(scenario: dict[str, Any]) -> dict[str, int]:
    """Map trigger kinds to scheduled match minutes from scenario JSON."""
    schedule: dict[str, int] = {}
    trigger = scenario.get("trigger")
    if trigger:
        schedule[str(trigger["kind"])] = int(trigger.get("time", 0))
    for item in scenario.get("triggers", []):
        schedule[str(item["kind"])] = int(item.get("time", 0))
    return schedule


def compute_intervention_timing(
    scenario: dict[str, Any],
    event_schedule: dict[str, int],
) -> dict[str, int]:
    """Engine-derived optimal intervention minutes for this scenario."""
    timing: dict[str, int] = {}
    transit_delay_t = event_schedule.get("transit_delay")
    if transit_delay_t is not None:
        # After transit_delay executes; before crowd_density_spike (default +3 min).
        timing["transit_reroute"] = transit_delay_t + 3
    match_end_t = event_schedule.get("match_end")
    if match_end_t is not None:
        timing["deploy_deescalation"] = match_end_t + 1
    controversial_t = event_schedule.get("controversial_call")
    if controversial_t is not None:
        timing["official_clarification"] = controversial_t + 18
        timing["platform_rumor_throttle"] = controversial_t + 10
    return timing


def _timing_hints(
    event_schedule: dict[str, int],
    intervention_timing: dict[str, int],
) -> list[str]:
    hints: list[str] = []
    if "transit_delay" in event_schedule:
        td = event_schedule["transit_delay"]
        optimal = intervention_timing.get("transit_reroute", td + 3)
        hints.append(
            f"CRITICAL: transit_delay fires at t={td}. "
            f"transit_reroute at t={td} is INEFFECTIVE (same-minute race). "
            f"Use t={td + 1}..{td + 3}; engine optimal t={optimal}."
        )
    return hints


@lru_cache(maxsize=16)
def _cached_baseline(scenario_path: str, until: int) -> str:
    """JSON cache key for run_scenario W0 results."""
    w0 = run_scenario(scenario_path, world_id="W0", until=until)
    return json.dumps(w0, sort_keys=True, default=str)


def gather_intervention_context(
    scenario_path: str | Path,
    *,
    until: int = 120,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Run W0 + intervention worlds; return dominant path and best cut points."""
    path = str(Path(scenario_path).resolve())
    scenario = load_scenario(path)

    if use_cache:
        w0 = json.loads(_cached_baseline(path, until))
    else:
        w0 = run_scenario(path, world_id="W0", until=until)

    dbg = analyze_result(w0)
    intervention_runs: list[dict[str, Any]] = []
    for world_id in _INTERVENTION_WORLDS:
        intervention_runs.append(run_scenario(path, world_id=world_id, until=until))

    cut_points = find_best_cut_points(w0, intervention_runs)
    top_cuts = cut_points[:5]

    init = scenario.get("initial_state", {})
    resources = {**scenario.get("resources", {}), **scenario.get("resources_override", {})}
    hints: list[str] = []

    if resources.get("official_comm_channel", 1) <= 0:
        hints.append(
            "official_comm_channel is 0: do NOT propose official_clarification."
        )
    misinfo = float(init.get("misinfo_confidence", 0.0))
    velocity = float(init.get("platform_velocity", 0.0))
    if misinfo > 0.5 or velocity > 0.5:
        hints.append(
            "High misinfo/platform velocity: prefer platform_rumor_throttle over "
            "official_clarification for rumor-chain scenarios."
        )
    if float(init.get("heat_stress", 0.0)) > 0.7 or float(init.get("transit_pressure", 0.0)) > 0.6:
        hints.append(
            "Heat/transit pressure high: transit_reroute often cuts panic before crowd_push."
        )

    event_schedule = build_event_schedule(scenario)
    intervention_timing = compute_intervention_timing(scenario, event_schedule)
    hints.extend(_timing_hints(event_schedule, intervention_timing))

    if top_cuts:
        best = top_cuts[0]
        hints.append(
            f"Engine best cut: {best['intervention']} before {best['before']} "
            f"(risk_reduction={best['risk_reduction']})."
        )
        if best.get("intervention") == "transit_reroute" and "transit_reroute" in intervention_timing:
            hints.append(
                f"Use transit_reroute at t={intervention_timing['transit_reroute']} "
                f"(matches W4 world intervention)."
            )

    return {
        "scenario_id": scenario.get("scenario_id", ""),
        "checkpoint_minute": proposal_checkpoint(scenario),
        "event_schedule": event_schedule,
        "intervention_timing": intervention_timing,
        "baseline_w0": {
            "dominant_path": dbg.dominant_risk_path() or w0.get("dominant_path", []),
            "final_risk": w0.get("final_risk", {}),
            "resource_bottlenecks": dbg.resource_bottlenecks(),
        },
        "best_cut_points": top_cuts,
        "recommended_interventions": [cp["intervention"] for cp in top_cuts[:3]],
        "scenario_hints": hints,
    }


def clear_context_cache() -> None:
    _cached_baseline.cache_clear()
