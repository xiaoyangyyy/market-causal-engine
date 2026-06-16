#!/usr/bin/env python3
"""Full catalog LLM pipeline: claims → refine → fit → eval → reproduce-benchmark."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "benchmark" / "full_llm_claims.log"
PIPELINE_LOG = ROOT / "data" / "benchmark" / "full_llm_pipeline.log"


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    PIPELINE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _env() -> dict[str, str]:
    return {**dict(os.environ), "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}


def _run(label: str, cmd: list[str]) -> None:
    _log(f"START {label}")
    proc = subprocess.run(cmd, cwd=ROOT, env=_env(), check=False)
    if proc.returncode != 0:
        raise SystemExit(f"{label} failed (exit {proc.returncode})")
    _log(f"DONE {label}")


def _claims_done() -> bool:
    if not LOG_PATH.exists():
        return False
    text = LOG_PATH.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return False
    try:
        data = json.loads(text.splitlines()[-1] if '"attempted"' not in text else text)
        if isinstance(data, dict) and "attempted" in data:
            return True
    except json.JSONDecodeError:
        pass
    if '"attempted"' in text and text.rstrip().endswith("}"):
        return True
    return False


def main() -> int:
    py = sys.executable
    sys.path.insert(0, str(ROOT))

    from market_causal_engine.extraction.llm_config import load_llm_config

    llm = load_llm_config()
    if not llm.enabled:
        _log("ERROR: LLM API key not configured")
        return 1

    if not _claims_done():
        _log("Running full LLM claim extraction (all events, force)...")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("w", encoding="utf-8") as logfh:
            proc = subprocess.run(
                [py, str(ROOT / "scripts" / "run_catalog_causal_claims.py"), "--all", "--use-llm", "--force"],
                cwd=ROOT,
                env=_env(),
                stdout=logfh,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if proc.returncode != 0:
            _log(f"LLM claims failed (exit {proc.returncode})")
            return proc.returncode
        _log("LLM claims complete")
    else:
        _log("LLM claims log already complete — skipping extraction")

    _run("Offline refine", [py, str(ROOT / "scripts" / "refine_catalog_claims.py")])
    _run("Fit catalog stack", [py, str(ROOT / "scripts" / "fit_catalog_learned.py")])

    from scripts.run_catalog_quality_pipeline import eval_metrics

    metrics = eval_metrics()
    out_path = ROOT / "data" / "benchmark" / "catalog_quality_pipeline_result.json"
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _log(f"Catalog eval: {json.dumps(metrics)}")

    _run("Reproduce benchmark", [py, str(ROOT / "scripts" / "reproduce_benchmark.py")])

    latest = ROOT / "results" / "reproduce" / "LATEST.json"
    if latest.exists():
        headline = json.loads(latest.read_text(encoding="utf-8")).get("headline_table", {})
        _log(f"Headline: {json.dumps(headline)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
