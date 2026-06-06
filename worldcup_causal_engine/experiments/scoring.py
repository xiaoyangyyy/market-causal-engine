"""Explainability scoring: Kernel vs LLM baseline."""

from __future__ import annotations

from typing import Any

from worldcup_causal_engine.reverse import analyze_result, diff_results


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def score_kernel(kernel_result: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, float]:
    dbg = analyze_result(kernel_result)
    traceability = 1.0 if kernel_result.get("trace") else 0.0
    consistency = 1.0

    why_sample = dbg.why_not_happen("riot_signal")
    not_happen = 1.0 if why_sample.get("reason") else 0.5

    intervention_diff = 0.0
    if baseline:
        diff = diff_results(baseline, kernel_result)
        intervention_diff = 1.0 if diff.get("diverged") else 0.0

    bottlenecks = dbg.resource_bottlenecks()
    bottleneck_score = 1.0 if bottlenecks or not kernel_result.get("resource_bottlenecks") else 0.5
    if kernel_result.get("resource_bottlenecks"):
        kernel_bn = {b["resource"] for b in kernel_result["resource_bottlenecks"]}
        dbg_bn = {b["resource"] for b in bottlenecks}
        bottleneck_score = 1.0 if kernel_bn <= dbg_bn or kernel_bn == dbg_bn else 0.5

    return {
        "traceability": traceability,
        "consistency": consistency,
        "not_happen_explanation": not_happen,
        "intervention_diff": intervention_diff,
        "bottleneck_localization": bottleneck_score,
    }


def score_llm_run(
    llm_output: dict[str, Any],
    scenario_resources: dict[str, float] | None = None,
) -> dict[str, float]:
    reasoning = llm_output.get("reasoning", "")
    traceability = 1.0 if len(reasoning) > 50 else (0.5 if reasoning else 0.0)

    dominant = llm_output.get("dominant_path", [])
    consistency = 1.0 if dominant else 0.0

    not_happen = 1.0 if any(
        kw in reasoning.lower()
        for kw in (
            "did not", "not happen", "didn't happen", "blocked", "未发生", "没有发生",
            "did not occur", "failed to", "prevented", "without", "never reached",
        )
    ) else 0.0

    intervention_diff = 1.0 if llm_output.get("best_cut_points") else 0.0

    bn = llm_output.get("resource_bottlenecks", [])
    bottleneck_score = 0.0
    if bn:
        bottleneck_score = 0.5
        if scenario_resources:
            for item in bn:
                if isinstance(item, str):
                    res = item
                elif isinstance(item, dict):
                    res = item.get("resource", "")
                else:
                    continue
                if scenario_resources.get(res, 1) == 0:
                    bottleneck_score = 1.0
                    break

    return {
        "traceability": traceability,
        "consistency": consistency,
        "not_happen_explanation": not_happen,
        "intervention_diff": intervention_diff,
        "bottleneck_localization": bottleneck_score,
    }


def score_llm_consistency(runs: list[dict[str, Any]]) -> float:
    if len(runs) < 2:
        return 1.0
    paths = [set(r.get("dominant_path", [])) for r in runs]
    scores = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            scores.append(_jaccard(paths[i], paths[j]))
    return sum(scores) / len(scores) if scores else 0.0


def compare_explainability(
    kernel_w0: dict[str, Any],
    kernel_w1: dict[str, Any],
    llm_runs_w0: list[dict[str, Any]],
    llm_runs_w1: list[dict[str, Any]],
    scenario_resources: dict[str, float] | None = None,
) -> dict[str, Any]:
    kernel_scores = score_kernel(kernel_w1, kernel_w0)
    llm_w0_scores = [score_llm_run(r, scenario_resources) for r in llm_runs_w0]
    llm_w1_scores = [score_llm_run(r, scenario_resources) for r in llm_runs_w1]

    def avg(scores: list[dict[str, float]]) -> dict[str, float]:
        if not scores:
            return {k: 0.0 for k in kernel_scores}
        keys = scores[0].keys()
        return {k: sum(s[k] for s in scores) / len(scores) for k in keys}

    llm_w0_avg = avg(llm_w0_scores)
    llm_w1_avg = avg(llm_w1_scores)
    llm_w0_avg["consistency"] = score_llm_consistency(llm_runs_w0)
    llm_w1_avg["consistency"] = score_llm_consistency(llm_runs_w1)

    llm_combined = {
        k: (llm_w0_avg[k] + llm_w1_avg[k]) / 2 for k in kernel_scores
    }

    return {
        "kernel": kernel_scores,
        "llm": llm_combined,
        "llm_w0": llm_w0_avg,
        "llm_w1": llm_w1_avg,
        "dimensions": list(kernel_scores.keys()),
    }
