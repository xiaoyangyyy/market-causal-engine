#!/usr/bin/env python3
"""Step E: one-click benchmark reproduction + validation manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "results" / "reproduce"
REPRO_SEED = 42


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_pytest(*, smoke: bool) -> dict[str, Any]:
    if smoke:
        targets = [
            "tests/test_benchmark.py::test_benchmark_runner_smoke",
            "tests/test_label_quality.py",
            "tests/test_outcome_layer.py",
            "tests/test_pit_hardening.py",
            "tests/test_step_d_demo.py::test_build_killer_demo_nflx",
        ]
        cmd = [sys.executable, "-m", "pytest", "-q", *targets]
    else:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--ignore=tests/test_phase4.py",
            "--ignore=tests/test_phase5_phase6.py",
            "--ignore=tests/test_phase7_phase8.py",
            "--ignore=tests/test_phase_c.py",
            "--ignore=tests/test_compiler.py",
            "--ignore=tests/test_evidence.py",
            "--ignore=tests/test_experiments.py",
            "--ignore=tests/test_reverse.py",
            "--ignore=tests/test_mechanisms.py",
            "--ignore=tests/test_kernel.py",
            "--ignore=tests/test_llm_proposer.py",
        ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-1000:] if proc.stderr else "",
    }


def _run_pit_audit() -> dict[str, Any]:
    from market_causal_engine.benchmark.validation import CASE_STUDY_ABLATION_IDS
    from market_causal_engine.platform.pit_hardening import audit_case_study, summarize_pit_compliance

    reports = []
    for case_id in CASE_STUDY_ABLATION_IDS:
        try:
            reports.append(audit_case_study(case_id, as_of_minutes=120))
        except FileNotFoundError:
            continue
    summary = summarize_pit_compliance(reports)
    return {"summary": summary, "cases": reports}


def _run_benchmark(*, max_events: int, until: int, run_ablation: bool) -> dict[str, Any]:
    from market_causal_engine.benchmark.runner import BenchmarkConfig, BenchmarkRunner

    out_dir = ROOT / "results" / "benchmark" / "reproduce"
    config = BenchmarkConfig(
        max_events_per_corpus=max_events,
        until=until,
        seed=REPRO_SEED,
        run_ablation=run_ablation,
        run_sensitivity=False,
        output_dir=out_dir,
    )
    report = BenchmarkRunner(config).run()
    headline = report.get("headline") or {}
    catalog = report.get("catalog_only") or {}
    return {
        "run_id": report.get("run_id"),
        "errors": report.get("errors") or [],
        "headline": {
            "real_label_n": headline.get("real_label_n"),
            "real_label_direction_accuracy": headline.get("real_label_direction_accuracy"),
            "placebo_false_positive_rate": headline.get("placebo_false_positive_rate"),
            "real_label_catalog_path_n": headline.get("real_label_catalog_path_n"),
        },
        "catalog_only": {
            "catalog_only_direction_accuracy": catalog.get("catalog_only_direction_accuracy"),
            "catalog_only_n": catalog.get("catalog_only_n"),
        },
        "out_of_time": report.get("out_of_time"),
        "pit_compliance": report.get("pit_compliance"),
        "artifacts": report.get("artifacts"),
    }


def _run_catalog_only(*, max_events: int | None) -> dict[str, Any]:
    from market_causal_engine.benchmark.catalog_eval import eval_catalog_only_metrics

    return eval_catalog_only_metrics(max_events=max_events)


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def reproduce(
    *,
    smoke: bool = False,
    skip_tests: bool = False,
    max_events: int | None = None,
    until: int | None = None,
    catalog_sample: int | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    if smoke:
        max_events = max_events if max_events is not None else 20
        until = until if until is not None else 60
        catalog_sample = catalog_sample if catalog_sample is not None else 40
    else:
        max_events = max_events if max_events is not None else 200
        until = until if until is not None else 120
        catalog_sample = catalog_sample  # None = full quality-eligible set

    out = output_dir or DEFAULT_OUTPUT
    manifest: dict[str, Any] = {
        "generated_at": _utc_now_iso(),
        "mode": "smoke" if smoke else "full",
        "seed": REPRO_SEED,
        "config": {
            "max_events_per_corpus": max_events,
            "until": until,
            "catalog_sample": catalog_sample,
        },
        "steps": {},
    }

    if not skip_tests:
        manifest["steps"]["pytest"] = _run_pytest(smoke=smoke)
        if not manifest["steps"]["pytest"]["ok"]:
            manifest["status"] = "failed"
            manifest["failed_step"] = "pytest"
            _write_manifest(out / "LATEST.json", manifest)
            return manifest

    manifest["steps"]["pit_audit"] = _run_pit_audit()
    manifest["steps"]["benchmark"] = _run_benchmark(
        max_events=max_events,
        until=until,
        run_ablation=True,
    )
    manifest["steps"]["catalog_only"] = _run_catalog_only(max_events=catalog_sample)

    errors = manifest["steps"]["benchmark"].get("errors") or []
    pit_ok = manifest["steps"]["pit_audit"]["summary"].get("all_passed", False)
    manifest["status"] = "ok" if pit_ok and not errors else "failed"
    if not pit_ok:
        manifest["failed_step"] = "pit_audit"
    elif errors:
        manifest["failed_step"] = "benchmark"

    manifest["headline_table"] = {
        "catalog_only_direction_accuracy": manifest["steps"]["catalog_only"].get(
            "catalog_only_direction_accuracy"
        ),
        "catalog_only_n": manifest["steps"]["catalog_only"].get("catalog_only_n"),
        "real_label_direction_accuracy": manifest["steps"]["benchmark"]["headline"].get(
            "real_label_direction_accuracy"
        ),
        "placebo_false_positive_rate": manifest["steps"]["benchmark"]["headline"].get(
            "placebo_false_positive_rate"
        ),
        "oot_test_direction_accuracy": (manifest["steps"]["benchmark"].get("out_of_time") or {}).get(
            "test_direction_accuracy"
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _write_manifest(out / f"reproduce_{stamp}.json", manifest)
    _write_manifest(out / "LATEST.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce headline benchmark metrics")
    parser.add_argument("--smoke", action="store_true", help="Fast CI-sized run")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--until", type=int, default=None)
    parser.add_argument("--catalog-sample", type=int, default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    manifest = reproduce(
        smoke=args.smoke,
        skip_tests=args.skip_tests,
        max_events=args.max_events,
        until=args.until,
        catalog_sample=args.catalog_sample,
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(manifest.get("headline_table") or {}, indent=2))
    print(f"\nstatus={manifest.get('status')} manifest={Path(args.output_dir) / 'LATEST.json'}")
    return 0 if manifest.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
