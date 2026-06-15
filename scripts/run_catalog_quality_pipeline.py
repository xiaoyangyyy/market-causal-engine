"""Full catalog quality pipeline: heuristic LLM → fallback upgrade → fit → eval."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _counts() -> dict[str, int]:
    sys.path.insert(0, str(ROOT))
    from market_causal_engine.benchmark.catalog.claim_quality import is_heuristic_claims_doc, is_llm_claims_doc
    from market_causal_engine.benchmark.catalog.claims import load_catalog_claims
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
    from market_causal_engine.benchmark.models import load_corpus

    events = [
        e
        for e in load_corpus("earnings_sp500_2016_2025", max_events=None)
        if _has_usable_atoms(e.event_id)
    ]
    llm = heur = fallback = 0
    for event in events:
        doc = load_catalog_claims(event.event_id)
        if not doc or not doc.get("accepted"):
            continue
        if is_heuristic_claims_doc(doc):
            heur += 1
        elif is_llm_claims_doc(doc):
            llm += 1
            if doc.get("llm_proposer") == "llm_atom_fallback":
                fallback += 1
    return {"llm": llm, "heuristic": heur, "atom_fallback": fallback}


def _run_claims_batch(py: str, env: dict[str, str], extra_args: list[str]) -> subprocess.CompletedProcess:
    cmd = [py, str(ROOT / "scripts" / "run_catalog_causal_claims.py"), "--all", "--use-llm", "--force", *extra_args]
    return subprocess.run(cmd, cwd=ROOT, env=env, check=False)


def _run_until_clear(
    label: str,
    py: str,
    env: dict[str, str],
    extra_args: list[str],
    *,
    count_key: str,
    max_rounds: int = 2,
) -> None:
    idle_rounds = 0
    rounds = 0
    while True:
        before = _counts()
        remaining = before[count_key]
        print(f"\n=== {label} === remaining={remaining}", flush=True)
        if remaining == 0:
            print(f"{label}: done", flush=True)
            return
        if rounds >= max_rounds:
            print(f"{label}: stopping after {max_rounds} rounds ({remaining} left)", flush=True)
            return

        rounds += 1
        proc = _run_claims_batch(py, env, extra_args)
        after = _counts()
        print(
            f"{label} exit={proc.returncode} {count_key}: {before[count_key]} -> {after[count_key]}",
            flush=True,
        )
        if after[count_key] >= before[count_key]:
            idle_rounds += 1
            wait_sec = min(300, 60 * idle_rounds)
            print(f"{label}: no progress (API may be down), sleep {wait_sec}s", flush=True)
            time.sleep(wait_sec)
            if idle_rounds >= 20:
                raise SystemExit(f"{label}: stalled after 20 idle rounds, {after[count_key]} left")
        else:
            idle_rounds = 0


def eval_metrics() -> dict:
    sys.path.insert(0, str(ROOT))
    from market_causal_engine.benchmark.catalog.claim_quality import (
        is_heuristic_claims_doc,
        is_llm_claims_doc,
        load_catalog_claims_policy,
    )
    from market_causal_engine.benchmark.catalog.claims import has_effective_catalog_claims, load_catalog_claims
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
    from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event
    from market_causal_engine.benchmark.models import load_corpus
    from market_causal_engine.benchmark.replay import infer_simulated_direction
    from market_causal_engine.learned.store import reload_learned_store

    reload_learned_store()
    policy = load_catalog_claims_policy()
    events = [
        e
        for e in load_corpus("earnings_sp500_2016_2025", max_events=None)
        if _has_usable_atoms(e.event_id)
    ]
    llm = heur = quality = 0
    for event in events:
        doc = load_catalog_claims(event.event_id)
        if not doc or not doc.get("accepted"):
            continue
        if is_llm_claims_doc(doc):
            llm += 1
        elif is_heuristic_claims_doc(doc):
            heur += 1
        if has_effective_catalog_claims(event.event_id, policy=policy):
            quality += 1

    ok = n = 0
    for event in events:
        if not has_effective_catalog_claims(event.event_id, policy=policy):
            continue
        obs = event.observed_outcomes.get("direction")
        if obs not in ("up", "down", "neutral"):
            continue
        result = replay_catalog_feed_event(event, until=60)
        pred = infer_simulated_direction(result, event=event.to_dict())
        n += 1
        if pred == obs:
            ok += 1

    fit_path = ROOT / "data" / "market" / "learned" / "catalog_fit_summary.json"
    fit = json.loads(fit_path.read_text(encoding="utf-8")) if fit_path.exists() else {}

    return {
        "llm_events": llm,
        "heuristic_events": heur,
        "quality_eligible": quality,
        "catalog_only_acc": round(ok / n, 4) if n else None,
        "catalog_only_n": n,
        "direction_holdout": fit.get("catalog_direction_holdout_accuracy"),
        "direction_train": fit.get("catalog_direction_train_accuracy"),
    }


def main() -> int:
    py = sys.executable
    env = {**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1"}

    print("Starting counts:", json.dumps(_counts()), flush=True)

    _run_until_clear(
        "Heuristic → LLM",
        py,
        env,
        ["--heuristic-only"],
        count_key="heuristic",
    )
    _run_until_clear(
        "Atom-fallback upgrade",
        py,
        env,
        ["--atom-fallback-only"],
        count_key="atom_fallback",
    )

    print("\n=== Fit catalog learned stack ===", flush=True)
    fit_proc = subprocess.run([py, str(ROOT / "scripts" / "fit_catalog_learned.py")], cwd=ROOT, env=env, check=False)
    if fit_proc.returncode != 0:
        return fit_proc.returncode

    metrics = eval_metrics()
    out_path = ROOT / "data" / "benchmark" / "catalog_quality_pipeline_result.json"
    out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n=== Final metrics ===", flush=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
