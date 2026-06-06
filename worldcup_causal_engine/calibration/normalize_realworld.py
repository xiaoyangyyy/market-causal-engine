"""Normalize downloaded public facts into Observation JSONL per scenario."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_causal_engine.calibration.downloaders.qatar_wc2022_public import (
    SCENARIO_MAP,
    PUBLIC_FACTS,
)
from worldcup_causal_engine.calibration.downloaders.normalize import normalize_to_observations_jsonl


def _gdelt_rumor_adjustment(raw_dir: Path, scenario_proxy: str) -> float | None:
    stats_path = raw_dir / "gdelt_japan_spain_var_stats.json"
    if not stats_path.exists() or scenario_proxy != "S1":
        return None
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    peak = int(stats.get("max", 0))
    if peak <= 0:
        return None
    # Heuristic: 150+ articles in 15-min bucket => high controversy
    return min(1.0, max(0.5, peak / 200.0))


def build_observations_for_scenario(
    scenario_proxy: str,
    *,
    world_id: str = "W0",
    raw_dir: str | Path = "data/calibration_raw",
) -> list[dict[str, Any]]:
    scenario_id = SCENARIO_MAP[scenario_proxy]
    raw = Path(raw_dir)
    records: list[dict[str, Any]] = []

    for fact in PUBLIC_FACTS:
        if fact.scenario_proxy != scenario_proxy:
            continue
        for obs in fact.observations:
            value = float(obs["value"])
            if obs["key"] == "rumor_volume_index":
                adj = _gdelt_rumor_adjustment(raw, scenario_proxy)
                if adj is not None:
                    value = adj
            records.append(
                {
                    "scenario_id": scenario_id,
                    "world_id": world_id,
                    "time_bucket": obs.get("time_bucket", "final"),
                    "key": obs["key"],
                    "value": round(value, 4),
                    "weight": float(obs.get("weight", 1.0)),
                    "meta": {
                        "fact_id": fact.fact_id,
                        "source": fact.source,
                        "url": fact.url,
                    },
                }
            )
    return records


def write_all_observation_files(
    *,
    raw_dir: str | Path = "data/calibration_raw",
    out_dir: str | Path = "data/observations",
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for proxy in ("S1", "S2", "S3"):
        records = build_observations_for_scenario(proxy, raw_dir=raw_dir)
        path = out / f"real_qatar2022_{proxy}_w0.jsonl"
        normalize_to_observations_jsonl(records, out_path=path)
        written[proxy] = str(path)
    return written
