"""Ablation and experiment metrics."""

from __future__ import annotations

from typing import Any


def count_blocked_events(result: dict[str, Any]) -> int:
    return sum(1 for e in result.get("trace", []) if e.get("action") == "blocked")


def path_length(result: dict[str, Any]) -> int:
    return len(result.get("dominant_path", []))


def compute_ablation_metrics(
    result: dict[str, Any],
    full_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace = result.get("trace", [])
    has_trace = bool(trace)
    blocked = count_blocked_events(result)

    verbal = result.get("final_risk", {}).get("verbal_conflict", 0.0)
    scuffle = result.get("final_risk", {}).get("scuffle", 0.0)

    intervention_effect = False
    if full_baseline and result.get("world_id", "W0") != "W0":
        base_v = full_baseline.get("final_risk", {}).get("verbal_conflict", 0.0)
        base_p = full_baseline.get("final_risk", {}).get("panic", 0.0)
        run_p = result.get("final_risk", {}).get("panic", 0.0)
        intervention_effect = verbal < base_v or run_p < base_p

    risk_deltas = []
    for entry in trace:
        if entry.get("action") == "commit":
            for key in ("verbal_conflict_risk", "scuffle_risk", "panic_risk"):
                if key in entry.get("patch", {}):
                    risk_deltas.append(entry["patch"][key])
    always_escalate = len(risk_deltas) > 1 and all(d >= 0 for d in risk_deltas)

    return {
        "final_verbal_conflict_risk": verbal,
        "final_scuffle_risk": scuffle,
        "final_panic_risk": result.get("final_risk", {}).get("panic", 0.0),
        "path_length": path_length(result),
        "blocked_events_count": blocked,
        "unexplained_blocks": None if has_trace else blocked,
        "always_escalate": always_escalate,
        "intervention_effect_visible": intervention_effect,
        "has_trace": has_trace,
        "trace_entries": len(trace),
    }
