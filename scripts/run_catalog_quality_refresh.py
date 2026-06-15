"""LLM quality refresh pipeline: re-extract eligible events → refine → fit → eval."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "benchmark" / "catalog_quality_refresh.log"


def _run(label: str, cmd: list[str], env: dict[str, str]) -> None:
    print(f"\n=== {label} ===", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {proc.returncode}")


def main() -> int:
    py = sys.executable
    import os

    env = {**dict(os.environ), "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}

    sys.path.insert(0, str(ROOT))
    from market_causal_engine.benchmark.catalog.claim_quality import (
        DEFAULT_LLM_QUALITY_POLICY,
        apply_catalog_claims_policy,
    )
    from market_causal_engine.benchmark.catalog.claims import load_catalog_claims
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
    from market_causal_engine.benchmark.models import load_corpus
    from market_causal_engine.extraction.llm_config import load_llm_config

    llm = load_llm_config()
    if not llm.enabled:
        print(
            json.dumps(
                {
                    "error": "LLM API key not configured",
                    "hint": "Copy .env.example → .env and set ZHISUAN_API_KEY or OPENAI_API_KEY",
                },
                indent=2,
            ),
            flush=True,
        )
        return 1

    events = [
        e
        for e in load_corpus("earnings_sp500_2016_2025", max_events=None)
        if _has_usable_atoms(e.event_id)
    ]
    refresh_n = sum(
        1
        for e in events
        if (doc := load_catalog_claims(e.event_id))
        and doc.get("accepted")
        and doc.get("llm_proposer") == "llm_event"
        and apply_catalog_claims_policy(doc, DEFAULT_LLM_QUALITY_POLICY) is not None
    )
    print(json.dumps({"refresh_events": refresh_n, "model": llm.model, "base_url": llm.base_url}), flush=True)

    _run(
        "LLM quality refresh",
        [py, str(ROOT / "scripts" / "run_catalog_causal_claims.py"), "--all", "--use-llm", "--force", "--quality-refresh"],
        env,
    )
    _run("Offline refine", [py, str(ROOT / "scripts" / "refine_catalog_claims.py")], env)
    _run("Fit catalog stack", [py, str(ROOT / "scripts" / "fit_catalog_learned.py")], env)

    from scripts.run_catalog_quality_pipeline import eval_metrics

    metrics = eval_metrics()
    out_path = ROOT / "data" / "benchmark" / "catalog_quality_pipeline_result.json"
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n=== Final metrics ===", flush=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
