"""Tests for Step D killer demo and World Cup split export."""

from __future__ import annotations

import json
from pathlib import Path

from market_causal_engine.demo.killer_demo import DEFAULT_DEMO_CASE, build_killer_demo


def test_build_killer_demo_nflx():
    demo = build_killer_demo(DEFAULT_DEMO_CASE, as_of=120)
    assert demo["case_id"] == DEFAULT_DEMO_CASE
    assert demo["hero"]["ticker"] == "NFLX"
    assert len(demo["event_timeline"]) >= 5
    assert demo["mechanism_path"]["steps"]
    assert demo["counterfactual"]["outcome_causal"]
    assert demo["channel_ablation"]
    assert len(demo["benchmark_neighbors"]) >= 1
    assert demo["limitations"]


def test_export_killer_demo_script(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "static"
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts" / "export_killer_demo.py"),
            "--out-dir",
            str(out),
            "--case",
            DEFAULT_DEMO_CASE,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (out / "index.html").exists()
    payload = json.loads((out / f"{DEFAULT_DEMO_CASE}.json").read_text(encoding="utf-8"))
    assert payload["hero"]["ticker"] == "NFLX"


def test_export_worldcup_legacy_smoke(tmp_path):
    import subprocess
    import sys

    out = tmp_path / "wc"
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts" / "export_worldcup_legacy.py"),
            "--output",
            str(out),
        ],
        check=True,
    )
    assert (out / "worldcup_causal_engine").is_dir()
    assert (out / "pyproject.toml").exists()
    assert (out / "SPLIT_MANIFEST.json").exists()
