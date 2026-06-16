"""Tests for Step E reproduce-benchmark harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_reproduce_benchmark_smoke_skip_tests(tmp_path):
    out = tmp_path / "reproduce"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "reproduce_benchmark.py"),
            "--smoke",
            "--skip-tests",
            "--max-events",
            "5",
            "--until",
            "30",
            "--catalog-sample",
            "8",
            "--output-dir",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    latest = out / "LATEST.json"
    assert latest.exists()
    manifest = json.loads(latest.read_text(encoding="utf-8"))
    assert manifest["status"] == "ok"
    assert manifest["steps"]["pit_audit"]["summary"]["all_passed"] is True
    assert manifest["headline_table"]["catalog_only_n"] is not None


def test_latest_manifest_has_headline_fields(tmp_path):
    out = tmp_path / "reproduce"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "reproduce_benchmark.py"),
            "--smoke",
            "--skip-tests",
            "--max-events",
            "3",
            "--catalog-sample",
            "5",
            "--output-dir",
            str(out),
        ],
        check=True,
        cwd=ROOT,
        timeout=600,
    )
    manifest = json.loads((out / "LATEST.json").read_text(encoding="utf-8"))
    table = manifest["headline_table"]
    for key in (
        "catalog_only_direction_accuracy",
        "real_label_direction_accuracy",
        "placebo_false_positive_rate",
    ):
        assert key in table
