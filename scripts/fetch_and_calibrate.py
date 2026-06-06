#!/usr/bin/env python3
"""Download public post-hoc data, normalize observations, run calibration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_causal_engine.calibration.downloaders.qatar_wc2022_public import SCENARIO_MAP
from worldcup_causal_engine.calibration.normalize_realworld import write_all_observation_files
from worldcup_causal_engine.calibration.observations import Dataset
from worldcup_causal_engine.calibration.report import write_calibration_report
from worldcup_causal_engine.calibration.search import random_search
from worldcup_causal_engine.scenarios import load_priors, run_scenario


SCENARIO_FILES = {
    "S1": "data/scenarios/S1_controversial_call_high_density.json",
    "S2": "data/scenarios/S2_team_eliminated_transit_delay.json",
    "S3": "data/scenarios/S3_heat_crowd_comm_delay.json",
}

PARAM_SPACES = {
    "S1": {
        "rumor_amplified": {"rumor_delta": (0.3, 1.0)},
        "offline_mood_shift": {"verbal_risk_delta": (0.01, 0.12)},
        "opposing_fans_contact": {
            "emit_conflict_delay": (2, 25),
            "colocation_threshold_crowd": (0.55, 0.95),
        },
        "verbal_conflict": {
            "verbal_risk_delta": (0.02, 0.15),
            "scuffle_risk_delta": (0.01, 0.08),
        },
    },
    "S2": {
        "fans_gather": {"density_delta": (0.05, 0.25), "pressure_delta": (0.05, 0.2)},
        "opposing_fans_contact": {"emit_conflict_delay": (2, 15)},
        "verbal_conflict": {"verbal_risk_delta": (0.1, 0.5)},
    },
    "S3": {
        "crowd_push": {"panic_delta": (0.1, 0.4)},
        "panic_signal": {"panic_delta": (0.1, 0.5)},
        "fans_gather": {"pressure_delta": (0.05, 0.25)},
        "verbal_conflict": {"verbal_risk_delta": (0.05, 0.35)},
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch real-world data and calibrate scenarios")
    parser.add_argument("--scenarios", default="S1,S2,S3", help="S1,S2,S3 proxies")
    parser.add_argument("--budget", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    root = ROOT
    raw_dir = root / "data" / "calibration_raw"
    obs_dir = root / "data" / "observations"
    out_dir = root / "results" / "calibration"

    if not args.skip_download:
        from worldcup_causal_engine.calibration.downloaders.qatar_wc2022_public import (
            QatarWC2022Downloader,
        )

        dl = QatarWC2022Downloader(raw_dir=raw_dir)
        result = dl.fetch(out_dir=raw_dir, query={"enrich_gdelt": True})
        print(f"Downloaded {len(result.files)} files to {raw_dir}")

    written = write_all_observation_files(raw_dir=raw_dir, out_dir=obs_dir)
    print("Observations:", written)

    base_priors = load_priors()
    summary: dict[str, object] = {"scenarios": {}}

    for proxy in args.scenarios.split(","):
        proxy = proxy.strip()
        if proxy not in SCENARIO_FILES:
            continue
        scenario_path = root / SCENARIO_FILES[proxy]
        obs_path = Path(written[proxy])
        dataset = Dataset.load_jsonl(obs_path)

        baseline = run_scenario(scenario_path, world_id="W0", until=120)
        baseline_loss = __import__(
            "worldcup_causal_engine.calibration.objective", fromlist=["evaluate_loss"]
        ).evaluate_loss(baseline, dataset)

        calib = random_search(
            scenario_path=str(scenario_path),
            world_id="W0",
            dataset=dataset,
            base_priors=base_priors,
            param_space=PARAM_SPACES[proxy],
            budget=args.budget,
            seed=args.seed,
            until=120,
        )

        calibrated = run_scenario(
            scenario_path,
            world_id="W0",
            until=120,
            priors_override=calib.best_priors_override,
        )
        calibrated_loss = __import__(
            "worldcup_causal_engine.calibration.objective", fromlist=["evaluate_loss"]
        ).evaluate_loss(calibrated, dataset)

        result_dict = calib.to_dict()
        result_dict["baseline_loss"] = baseline_loss.total
        result_dict["calibrated_loss"] = calibrated_loss.total
        result_dict["improvement"] = baseline_loss.total - calibrated_loss.total
        result_dict["calibrated_run"] = {
            "final_risk": calibrated.get("final_risk"),
            "dominant_path": calibrated.get("dominant_path"),
            "final_state": {
                k: calibrated["final_state"].get(k)
                for k in ("rumor_volume", "outrage_frame", "verbal_conflict_risk", "panic_risk")
                if calibrated.get("final_state")
            },
        }
        result_dict["scenario_proxy"] = proxy
        result_dict["real_world_mapping"] = SCENARIO_MAP[proxy]

        paths = write_calibration_report(
            result=result_dict,
            scenario_id=SCENARIO_MAP[proxy],
            observations_path=str(obs_path),
            baseline_result=baseline,
            out_dir=out_dir,
        )
        summary["scenarios"][proxy] = {
            "baseline_loss": baseline_loss.total,
            "calibrated_loss": calibrated_loss.total,
            "improvement": result_dict["improvement"],
            "report": paths,
        }
        print(
            f"{proxy}: baseline_loss={baseline_loss.total:.4f} -> "
            f"calibrated_loss={calibrated_loss.total:.4f} "
            f"(Δ={result_dict['improvement']:.4f})"
        )

    summary_path = out_dir / "real_world_calibration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Summary: {summary_path}")

    from worldcup_causal_engine.calibration.merge_priors import write_calibrated_priors

    priors_path = write_calibrated_priors(report_dir=out_dir)
    print(f"Merged priors: {priors_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
