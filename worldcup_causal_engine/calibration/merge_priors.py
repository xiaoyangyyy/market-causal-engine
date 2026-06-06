"""Merge per-scenario calibration reports into a single priors file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _load_base_priors() -> dict[str, dict[str, float]]:
    path = _project_root() / "data" / "priors" / "mechanisms_v0.1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_overrides_from_reports(
    report_dir: str | Path,
) -> list[tuple[str, dict[str, dict[str, float]], float]]:
    """Return (scenario_id, overrides, best_loss) sorted by scenario."""
    root = Path(report_dir)
    out: list[tuple[str, dict[str, dict[str, float]], float]] = []
    for path in sorted(root.glob("*_calibration_report.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cal = data.get("calibration", {})
        overrides = cal.get("best_priors_override", {})
        loss = float(cal.get("best_loss", 1.0))
        scenario_id = data.get("scenario_id", path.stem)
        if overrides:
            out.append((scenario_id, overrides, max(loss, 1e-6)))
    return out


def _merge_overrides(
    entries: list[tuple[str, dict[str, dict[str, float]], float]],
) -> dict[str, dict[str, float]]:
    """Weight-averaged merge; weight = 1 / best_loss (better fit => higher weight)."""
    accum: dict[str, dict[str, tuple[float, float]]] = {}
    for _sid, overrides, loss in entries:
        w = 1.0 / loss
        for mech, params in overrides.items():
            for key, value in params.items():
                prev = accum.setdefault(mech, {}).get(key)
                if prev is None:
                    accum[mech][key] = (float(value) * w, w)
                else:
                    s, sw = prev
                    accum[mech][key] = (s + float(value) * w, sw + w)

    merged: dict[str, dict[str, float]] = {}
    for mech, params in accum.items():
        merged[mech] = {}
        for key, (s, sw) in params.items():
            merged[mech][key] = round(s / sw, 6)
    return merged


def build_calibrated_priors(
    *,
    report_dir: str | Path | None = None,
    base_priors: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    base = base_priors or _load_base_priors()
    reports = _collect_overrides_from_reports(
        report_dir or _project_root() / "results" / "calibration"
    )
    by_scenario = {sid: ov for sid, ov, _ in reports}
    merged = _merge_overrides(reports)

    out: dict[str, Any] = {k: dict(v) for k, v in base.items() if not k.startswith("_")}
    for mech, params in merged.items():
        out.setdefault(mech, {}).update(params)

    out["_calibration_meta"] = {
        "version": "v0.2_calibrated",
        "base": "mechanisms_v0.1.json",
        "source_reports": [str(Path(report_dir or _project_root() / "results" / "calibration") / f"{sid}_calibration_report.json") for sid in by_scenario],
        "merge_strategy": "weighted_mean_by_inverse_loss",
        "merged_overrides": merged,
        "by_scenario_overrides": by_scenario,
    }
    return out


def write_calibrated_priors(
    out_path: str | Path | None = None,
    *,
    report_dir: str | Path | None = None,
) -> Path:
    path = Path(out_path or _project_root() / "data" / "priors" / "mechanisms_v0.2_calibrated.json")
    payload = build_calibrated_priors(report_dir=report_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def priors_for_scenario(
    priors_data: dict[str, Any],
    scenario_id: str,
) -> dict[str, dict[str, float]]:
    """Return mechanism priors dict (no _meta), optionally layered with scenario-specific overrides."""
    base = {k: dict(v) for k, v in priors_data.items() if not k.startswith("_")}
    meta = priors_data.get("_calibration_meta", {})
    scenario_overrides = meta.get("by_scenario_overrides", {}).get(scenario_id, {})
    if scenario_overrides:
        for mech, params in scenario_overrides.items():
            base.setdefault(mech, {}).update(params)
    return base
