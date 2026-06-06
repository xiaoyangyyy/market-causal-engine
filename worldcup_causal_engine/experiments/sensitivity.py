"""Mechanism parameter sensitivity analysis."""

from __future__ import annotations

import json
import random
from itertools import product
from pathlib import Path
from typing import Any

from worldcup_causal_engine.scenarios import _project_root, run_scenario

PARAM_GRID = {
    "rumor_amplified.rumor_delta": [0.2, 0.3, 0.4, 0.5, 0.6],
    "media_blame_frame.outrage_delta": [0.1, 0.2, 0.3, 0.4],
    "official_clarification.rumor_reduction": [0.1, 0.2, 0.3, 0.4],
    "police_trust": [0.3, 0.4, 0.5, 0.6, 0.7],
}


def _apply_override(priors_override: dict, key: str, value: float) -> None:
    if key == "police_trust":
        return
    mech, param = key.split(".", 1)
    priors_override.setdefault(mech, {})[param] = value


def run_sensitivity_grid(
    scenario: str = "S1",
    world_id: str = "W0",
    until: int = 120,
    output_dir: str | Path | None = None,
    max_runs: int = 100,
) -> dict[str, Any]:
    from worldcup_causal_engine.experiments.runner import resolve_scenario_path

    scenario_path = resolve_scenario_path(scenario)
    out_root = Path(output_dir) if output_dir else _project_root() / "results" / "experiment_sensitivity"
    out_root.mkdir(parents=True, exist_ok=True)

    mech_params = {k: v for k, v in PARAM_GRID.items() if k != "police_trust"}
    police_vals = PARAM_GRID["police_trust"]
    combos = list(product(*mech_params.values()))
    random.seed(42)
    if len(combos) * len(police_vals) > max_runs:
        combos = random.sample(combos, min(len(combos), max_runs // len(police_vals)))

    keys = list(mech_params.keys())
    rows: list[dict[str, Any]] = []

    for combo in combos:
        for police_trust in police_vals:
            priors_override: dict[str, dict[str, float]] = {}
            params_record: dict[str, float] = {"police_trust": police_trust}
            for key, val in zip(keys, combo):
                _apply_override(priors_override, key, val)
                params_record[key] = val

            result = run_scenario(
                scenario_path,
                world_id=world_id,
                until=until,
                priors_override=priors_override,
                state_override={"police_trust": police_trust},
            )
            rows.append({
                "params": params_record,
                "final_risk": result["final_risk"],
                "dominant_path": result.get("dominant_path", []),
                "path_signature": "→".join(result.get("dominant_path", [])),
            })

    path_signatures = {r["path_signature"] for r in rows}
    summary = {
        "experiment": "sensitivity",
        "scenario": scenario,
        "world_id": world_id,
        "runs": len(rows),
        "unique_path_signatures": len(path_signatures),
        "path_stable": len(path_signatures) <= 3,
        "verbal_conflict_range": [
            min(r["final_risk"]["verbal_conflict"] for r in rows),
            max(r["final_risk"]["verbal_conflict"] for r in rows),
        ],
        "results": rows,
    }
    (out_root / "sensitivity_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
