"""Calibration report writer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_calibration_report(
    *,
    result: dict[str, Any],
    scenario_id: str,
    observations_path: str,
    baseline_result: dict[str, Any] | None = None,
    out_dir: str | Path = "results/calibration",
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_id": scenario_id,
        "observations_path": observations_path,
        "calibration": result,
    }
    if baseline_result:
        payload["baseline"] = {
            "final_risk": baseline_result.get("final_risk"),
            "dominant_path": baseline_result.get("dominant_path"),
        }
        payload["calibrated_run"] = result.get("calibrated_run")

    json_path = out / f"{scenario_id}_calibration_report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# Calibration Report: {scenario_id}",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Observations: `{observations_path}`",
        f"- Search trials: {result.get('tried', 'n/a')}",
        f"- Best loss: **{result.get('best_loss', 'n/a')}**",
        "",
        "## Best prior overrides",
        "```json",
        json.dumps(result.get("best_priors_override", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Loss breakdown",
        "```json",
        json.dumps(result.get("best_breakdown", {}), indent=2, ensure_ascii=False),
        "```",
    ]
    if baseline_result:
        md_lines.extend(
            [
                "",
                "## Baseline vs calibrated final risk",
                f"- Baseline: `{baseline_result.get('final_risk')}`",
                f"- Calibrated: `{result.get('calibrated_run', {}).get('final_risk')}`",
            ]
        )

    md_path = out / f"{scenario_id}_calibration_report.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}
