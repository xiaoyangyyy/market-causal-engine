#!/usr/bin/env python3
"""Export World Cup legacy to a standalone directory (Step D split prep)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WORLDCUP_PACKAGE = "worldcup_causal_engine"
WORLDCUP_TESTS = [
    "test_phase4.py",
    "test_phase5_phase6.py",
    "test_phase7_phase8.py",
    "test_phase_c.py",
    "test_compiler.py",
    "test_evidence.py",
    "test_experiments.py",
    "test_reverse.py",
    "test_mechanisms.py",
    "test_kernel.py",
    "test_llm_proposer.py",
]
WORLDCUP_DATA_DIRS = [
    "data/scenarios",
    "data/interventions",
    "data/contracts",
    "data/observations",
    "data/calibration_raw",
    "data/feeds",
    "data/priors/mechanisms_v0.1.json",
    "data/priors/mechanisms_v0.2_calibrated.json",
    "data/priors/scenario_overrides",
]
WORLDCUP_DOCS = [
    "docs/00-完整方案.md",
    "docs/phase-01-核心引擎与主链路.md",
    "docs/phase-02-逆向调试与干预实验.md",
    "docs/phase-03-文本证据层.md",
    "docs/phase-04-完整实验与论文输出.md",
    "docs/experiment-report.md",
    "docs/calibration-data-sources.md",
    "docs/phase-05-06-架构.md",
    "docs/phase-07-08-架构.md",
]
WORLDCUP_SCRIPTS = [
    "scripts/plot_results.py",
    "scripts/build_manifest.py",
    "scripts/fetch_and_calibrate.py",
    "scripts/export_mdg.py",
    "scripts/merge_calibrated_priors.py",
]

PYPROJECT_STUB = """[project]
name = "worldcup-causal-engine"
version = "0.4.0"
description = "Trace-first runtime causal engine for World Cup crowd-risk simulation (legacy)"
requires-python = ">=3.10"
readme = "README.md"

[project.optional-dependencies]
dev = ["pytest>=7.0", "matplotlib>=3.7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
"""

README_STUB = """# World Cup Causal Engine (Legacy)

Extracted from [market-causal-engine](https://github.com/xiaoyangyyy/market-causal-engine) monorepo — **Step D split**.

Crowd-risk / media-opinion simulation for Qatar 2022 scenarios (S1–S6).  
The **market event** product lives in the separate `market-causal-engine` repository.

## Quick start

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
python -m worldcup_causal_engine.main \\
  --scenario data/scenarios/S1_controversial_call_high_density.json \\
  --world W0 --until 120 --explain
```

See `docs/00-完整方案.md` for architecture.
"""


def export_worldcup(out_dir: Path) -> dict[str, int]:
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    shutil.copytree(ROOT / WORLDCUP_PACKAGE, out_dir / WORLDCUP_PACKAGE)
    (out_dir / "tests").mkdir()
    for name in WORLDCUP_TESTS:
        src = ROOT / "tests" / name
        if src.exists():
            shutil.copy2(src, out_dir / "tests" / name)

    for rel in WORLDCUP_DATA_DIRS:
        src = ROOT / rel
        dst = out_dir / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    (out_dir / "docs").mkdir(exist_ok=True)
    for rel in WORLDCUP_DOCS:
        src = ROOT / rel
        if src.exists():
            shutil.copy2(src, out_dir / "docs" / src.name)

    scripts_out = out_dir / "scripts"
    scripts_out.mkdir(exist_ok=True)
    for rel in WORLDCUP_SCRIPTS:
        src = ROOT / rel
        if src.exists():
            shutil.copy2(src, scripts_out / src.name)

    if (ROOT / "paper").exists():
        shutil.copytree(ROOT / "paper", out_dir / "paper")
    if (ROOT / "results").exists():
        shutil.copytree(ROOT / "results", out_dir / "results")

    (out_dir / "pyproject.toml").write_text(PYPROJECT_STUB, encoding="utf-8")
    (out_dir / "README.md").write_text(README_STUB, encoding="utf-8")
    (out_dir / "requirements.txt").write_text("pytest>=7.0\nmatplotlib>=3.7\n", encoding="utf-8")

    manifest = {
        "source_monorepo": "market-causal-engine",
        "package": WORLDCUP_PACKAGE,
        "tests": WORLDCUP_TESTS,
        "note": "Run from monorepo: python scripts/export_worldcup_legacy.py --output dist/worldcup-causal-engine",
    }
    (out_dir / "SPLIT_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"files": sum(1 for _ in out_dir.rglob("*") if _.is_file())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export World Cup legacy to standalone directory")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "dist" / "worldcup-causal-engine"),
        help="Output directory",
    )
    args = parser.parse_args()
    stats = export_worldcup(Path(args.output))
    print(f"Exported World Cup legacy → {args.output} ({stats['files']} files)")
    print("Next: cd dist/worldcup-causal-engine && git init && git add . && git commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
