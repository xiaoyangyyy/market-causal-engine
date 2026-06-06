#!/usr/bin/env python3
"""Build reproducibility manifest with config hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    artifacts = [
        "data/priors/mechanisms_v0.1.json",
        "data/compiler_rules/v0.1.json",
        "data/scenarios/S1_controversial_call_high_density.json",
        "data/scenarios/S2_team_eliminated_transit_delay.json",
        "data/scenarios/S3_heat_crowd_comm_delay.json",
        "results/experiment_1/summary.json",
        "results/experiment_2/ablation_summary.json",
        "results/experiment_3/explainability_scores.json",
        "results/experiment_sensitivity/sensitivity_summary.json",
    ]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_seed_sensitivity": 42,
        "artifacts": {a: file_hash(ROOT / a) for a in artifacts},
    }
    out = ROOT / "results" / "reproducibility" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
