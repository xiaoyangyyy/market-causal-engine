"""Batch counterfactual estimation for case studies and benchmark corpora."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from market_causal_engine.case_study import list_case_studies
from market_causal_engine.benchmark.labels import fetch_ticker_daily_bars
from market_causal_engine.counterfactuals.estimate import estimate_outcome_causal

CASE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies"
BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark"
CF_OUT_DIR = BENCHMARK_DIR / "counterfactuals"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_case_counterfactuals(
    *,
    case_ids: list[str] | None = None,
    method: str = "synthetic_control",
    write_manifest: bool = True,
    bars_cache: dict[str, list] | None = None,
) -> dict[str, Any]:
    cases = case_ids or [c["case_id"] for c in list_case_studies()]
    cache = bars_cache or {}
    results: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    for case_id in cases:
        manifest_path = CASE_ROOT / case_id / "manifest.json"
        if not manifest_path.exists():
            errors.append({"case_id": case_id, "error": "manifest not found"})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ticker = str(manifest.get("ticker", "")).upper()
        event_date = str(manifest.get("event_date", ""))
        try:
            out = estimate_outcome_causal(
                ticker,
                event_date,
                method=method,  # type: ignore[arg-type]
                prefer_sc=True,
                run_placebo=True,
                bars_cache=cache,
            )
            out["case_id"] = case_id
            results[case_id] = out
            if write_manifest:
                out_path = CASE_ROOT / case_id / "outcome_causal.json"
                out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                manifest["outcome_causal"] = {
                    "method": out["method"],
                    "effect": out["effect"],
                    "observed_return": out["observed_return"],
                    "counterfactual_return": out["counterfactual_return"],
                    "placebo_rank": out.get("placebo_rank"),
                    "artifact": str(out_path.relative_to(CASE_ROOT.parent.parent.parent)),
                }
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append({"case_id": case_id, "ticker": ticker, "error": str(exc)})

    summary = {"cases": len(cases), "ok": len(results), "errors": errors, "results": results}
    CF_OUT_DIR.mkdir(parents=True, exist_ok=True)
    (CF_OUT_DIR / "case_studies_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def _iter_corpus(path: Path) -> Iterator[dict[str, Any]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def run_benchmark_counterfactuals(
    corpus_name: str = "earnings_sp500_2016_2025",
    *,
    method: str = "auto",
    major_only: bool = False,
    real_labels_only: bool = True,
    max_events: int | None = None,
    write_corpus: bool = True,
    bars_cache: dict[str, list] | None = None,
) -> dict[str, Any]:
    corpus_path = BENCHMARK_DIR / f"{corpus_name}.jsonl"
    if not corpus_path.exists():
        raise FileNotFoundError(corpus_path)

    cache = bars_cache or {}
    # Ensure market benchmarks are cached before bulk ticker fetches.
    for sym in ("SPY", "QQQ"):
        if sym not in cache or not cache[sym]:
            cache[sym] = fetch_ticker_daily_bars(sym)

    records = list(_iter_corpus(corpus_path))
    if real_labels_only:
        records = [r for r in records if not r.get("metadata", {}).get("synthetic_labels")]
    if major_only:
        records = [r for r in records if r.get("labels", {}).get("is_major_event")]
    if max_events is not None:
        records = records[:max_events]

    prefer_sc = method == "synthetic_control"
    out_lines: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    ok = 0
    enriched_map: dict[str, dict] = {}

    for rec in records:
        ticker = str(rec.get("ticker", "")).upper()
        event_date = str(rec.get("event_date", ""))
        event_id = str(rec.get("event_id", ""))
        try:
            cf = estimate_outcome_causal(
                ticker,
                event_date,
                method=method,  # type: ignore[arg-type]
                prefer_sc=prefer_sc,
                run_placebo=False,
                include_alternates=False,
                bars_cache=cache,
            )
            cf["event_id"] = event_id
            out_lines.append({"event_id": event_id, "ticker": ticker, "event_date": event_date, **cf})
            rec = dict(rec)
            rec["outcome_causal"] = {
                "method": cf["method"],
                "effect": cf["effect"],
                "observed_return": cf["observed_return"],
                "counterfactual_return": cf["counterfactual_return"],
                "pre_fit_rmse": cf.get("pre_fit_rmse"),
                "placebo_rank": cf.get("placebo_rank"),
            }
            enriched_map[str(rec.get("event_id"))] = rec["outcome_causal"]
            ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"event_id": event_id, "ticker": ticker, "error": str(exc)})
            out_lines.append({"event_id": event_id, "ticker": ticker, "event_date": event_date, "error": str(exc)})

    # Retry transient Yahoo failures once SPY/peer cache is warm.
    if errors:
        retry_errors: list[dict[str, str]] = []
        for err in errors:
            event_id = err["event_id"]
            rec = next(r for r in records if str(r.get("event_id")) == event_id)
            ticker = str(rec.get("ticker", "")).upper()
            event_date = str(rec.get("event_date", ""))
            try:
                cf = estimate_outcome_causal(
                    ticker,
                    event_date,
                    method=method,  # type: ignore[arg-type]
                    prefer_sc=prefer_sc,
                    run_placebo=False,
                    include_alternates=False,
                    bars_cache=cache,
                )
                cf["event_id"] = event_id
                out_lines = [r for r in out_lines if r.get("event_id") != event_id]
                out_lines.append({"event_id": event_id, "ticker": ticker, "event_date": event_date, **cf})
                rec = dict(rec)
                rec["outcome_causal"] = {
                    "method": cf["method"],
                    "effect": cf["effect"],
                    "observed_return": cf["observed_return"],
                    "counterfactual_return": cf["counterfactual_return"],
                    "pre_fit_rmse": cf.get("pre_fit_rmse"),
                    "placebo_rank": cf.get("placebo_rank"),
                }
                enriched_map[str(rec.get("event_id"))] = rec["outcome_causal"]
                ok += 1
            except Exception as exc:  # noqa: BLE001
                retry_errors.append({"event_id": event_id, "ticker": ticker, "error": str(exc)})
        errors = retry_errors

    CF_OUT_DIR.mkdir(parents=True, exist_ok=True)
    cf_path = CF_OUT_DIR / f"{corpus_name}.jsonl"
    cf_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_lines) + "\n", encoding="utf-8")

    if write_corpus:
        enriched: list[dict[str, Any]] = []
        for line in _iter_corpus(corpus_path):
            row = dict(line)
            eid = str(row.get("event_id", ""))
            if eid in enriched_map:
                row["outcome_causal"] = enriched_map[eid]
            enriched.append(row)
        corpus_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in enriched) + "\n", encoding="utf-8")

    stats = {
        "corpus": corpus_name,
        "attempted": len(records),
        "ok": ok,
        "errors": len(errors),
        "error_samples": errors[:20],
        "output": str(cf_path),
        "computed_at": _utc_now(),
    }
    (CF_OUT_DIR / f"{corpus_name}_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def run_full_phase1(
    *,
    benchmark_method: str = "abnormal_return",
    case_method: str = "synthetic_control",
) -> dict[str, Any]:
    """Run all case studies (SC) + full earnings benchmark (abnormal return bulk)."""
    cache: dict[str, list] = {}
    cases = run_case_counterfactuals(method=case_method, bars_cache=cache)
    benchmark = run_benchmark_counterfactuals(
        method=benchmark_method,
        real_labels_only=True,
        bars_cache=cache,
    )
    return {"cases": cases, "benchmark": benchmark, "computed_at": _utc_now()}
