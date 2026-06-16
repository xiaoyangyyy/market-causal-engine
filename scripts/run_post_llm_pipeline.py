#!/usr/bin/env python3
"""Wait for in-flight LLM claims job, then refine → fit → eval → reproduce."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "benchmark" / "full_llm_claims.log"
PIPELINE_LOG = ROOT / "data" / "benchmark" / "full_llm_pipeline_status.log"


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


def _claims_finished() -> bool:
    if LOG_PATH.exists():
        text = LOG_PATH.read_text(encoding="utf-8", errors="ignore").strip()
        if '"attempted"' in text:
            for line in reversed(text.splitlines()):
                line = line.strip()
                if line.startswith("{") and '"attempted"' in line:
                    try:
                        data = json.loads(line)
                        return int(data.get("ok", 0)) + int(len(data.get("errors", []))) >= int(
                            data.get("attempted", 0)
                        )
                    except json.JSONDecodeError:
                        pass
        if "1983/1983" in text:
            return True

    if _fresh_llm_count(time.strftime("%Y-%m-%d")) >= 1900:
        return True

    return False


def _fresh_llm_count(today: str) -> int:
    catalog = ROOT / "data" / "benchmark" / "catalog"
    if not catalog.exists():
        return 0
    n = 0
    for path in catalog.glob("*/causal_claims.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if str(doc.get("computed_at", "")).startswith(today) and doc.get("llm_proposer"):
            n += 1
    return n


def main() -> int:
    py = sys.executable
    sys.path.insert(0, str(ROOT))
    _log("Waiting for full LLM claims job to finish...")
    polls = 0
    while not _claims_finished():
        polls += 1
        if LOG_PATH.exists():
            tail = LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()[-1:]
            fresh = _fresh_llm_count(time.strftime("%Y-%m-%d"))
            _log(f"progress: fresh_llm={fresh}/1983 | " + (" | ".join(tail) if tail else "no log yet"))
        else:
            _log("waiting for log file...")
        time.sleep(120)
        if polls > 600:  # ~20 hours
            _log("TIMEOUT waiting for claims")
            return 1

    _log("Claims job finished")
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
