"""Ablation experiment runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_causal_engine.config import ABLATION_IDS, ABLATION_LABELS, KernelConfig
from worldcup_causal_engine.experiments.metrics import compute_ablation_metrics
from worldcup_causal_engine.scenarios import _project_root, run_scenario

FEED = _project_root() / "data" / "atoms" / "sample_match_feed.jsonl"
SCENARIOS = ["S1", "S2", "S3"]


def run_ablation(
    scenarios: list[str] | None = None,
    ablation_ids: list[str] | None = None,
    until: int = 120,
    output_dir: str | Path | None = None,
    use_feed_for_a6: bool = True,
) -> dict[str, Any]:
    scenarios = scenarios or SCENARIOS
    ablation_ids = ablation_ids or ABLATION_IDS
    out_root = Path(output_dir) if output_dir else _project_root() / "results" / "experiment_2"
    out_root.mkdir(parents=True, exist_ok=True)

    from worldcup_causal_engine.experiments.runner import resolve_scenario_path

    rows: list[dict[str, Any]] = []
    full_baselines: dict[str, dict[str, Any]] = {}

    for scenario_name in scenarios:
        scenario_path = resolve_scenario_path(scenario_name)
        full_path = out_root / f"{scenario_name}_full_W0.json"
        full_result = run_scenario(scenario_path, world_id="W0", until=until)
        full_path.write_text(json.dumps(full_result, indent=2, ensure_ascii=False), encoding="utf-8")
        full_baselines[scenario_name] = full_result

        full_metrics = compute_ablation_metrics(full_result)
        rows.append({
            "scenario_id": full_result["scenario_id"],
            "ablation_id": "full",
            "label": ABLATION_LABELS["full"],
            "world_id": "W0",
            **full_metrics,
            "dominant_path": full_result.get("dominant_path", []),
        })

        for ab_id in ablation_ids:
            if ab_id == "full":
                continue
            config = KernelConfig.ablation(ab_id)
            feed_path = None
            if ab_id == "A6" and use_feed_for_a6 and FEED.exists():
                feed_path = FEED

            world = "W0" if ab_id == "A5" else "W1"
            result = run_scenario(
                scenario_path,
                world_id=world,
                until=until,
                kernel_config=config,
                feed_path=feed_path,
            )

            fname = f"{scenario_name}_{ab_id}_W0.json"
            (out_root / fname).write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            metrics = compute_ablation_metrics(result, full_baselines.get(scenario_name))
            rows.append({
                "scenario_id": result["scenario_id"],
                "ablation_id": ab_id,
                "label": ABLATION_LABELS.get(ab_id, ab_id),
                "world_id": result.get("world_id", "W0"),
                **metrics,
                "dominant_path": result.get("dominant_path", []),
            })

    summary = {
        "experiment": "ablation",
        "runs": len(rows),
        "results": rows,
        "hypotheses": {
            "A1": "Paths lengthen; flag-gated events may execute spuriously",
            "A2": "Resource bottlenecks disappear; interventions always succeed",
            "A3": "Intervention timing distorted vs baseline",
            "A4": "Trace empty; blocked events not auditable",
            "A5": "W0=W1; no intervention effect measurable",
            "A6": "Feed atoms emit per-atom; path inflation vs clustered compile",
        },
    }
    (out_root / "ablation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
