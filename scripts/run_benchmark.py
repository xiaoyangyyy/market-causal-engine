"""Run event benchmark validation suite (P2)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.benchmark.labels import enrich_earnings_corpus
from market_causal_engine.benchmark.models import list_corpora
from market_causal_engine.benchmark.runner import BenchmarkConfig, BenchmarkRunner

EARNINGS_CORPUS = Path(__file__).resolve().parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Event benchmark: OOT, placebo, ablation")
    parser.add_argument("--list", action="store_true", help="List benchmark corpora")
    parser.add_argument("--run", action="store_true", help="Execute benchmark suite")
    parser.add_argument("--enrich-labels", action="store_true", help="Fetch real Yahoo labels for earnings corpus")
    parser.add_argument("--corpus", action="append", default=[], help="Corpus name (repeatable)")
    parser.add_argument("--max-events", type=int, default=None, help="Max events per corpus (default 200; use with --full for all)")
    parser.add_argument("--full", action="store_true", help="Full scale: all events, enrich labels, sensitivity")
    parser.add_argument("--until", type=int, default=120, help="Replay horizon (minutes)")
    parser.add_argument("--oot-cutoff", default="2022-01-01", help="Out-of-time split date")
    parser.add_argument("--no-ablation", action="store_true", help="Skip ablation suite")
    parser.add_argument("--sensitivity", action="store_true", help="Run ±10%% prior sensitivity (slow)")
    parser.add_argument("--no-placebo", action="store_true", help="Exclude placebo corpus")
    parser.add_argument("--output-dir", default="results/benchmark")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.list:
        for name, desc in list_corpora().items():
            print(f"{name}: {desc}")
        return 0

    if args.enrich_labels or args.full:
        print("Enriching earnings corpus with Yahoo daily labels...", flush=True)
        stats = enrich_earnings_corpus(EARNINGS_CORPUS, refresh_prices=args.full)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        if not args.run and not args.full:
            return 0

    if not args.run and not args.full:
        parser.print_help()
        return 1

    max_events = None if args.full else (args.max_events if args.max_events is not None else 200)
    corpora = args.corpus or None
    config = BenchmarkConfig(
        corpora=corpora,
        max_events_per_corpus=max_events,
        until=args.until,
        oot_cutoff_date=args.oot_cutoff,
        run_ablation=not args.no_ablation,
        run_sensitivity=args.sensitivity or args.full,
        sensitivity_sample=20 if args.full else 3,
        include_placebo=not args.no_placebo,
        output_dir=Path(args.output_dir),
        seed=args.seed,
    )
    print(f"Running benchmark (max_events_per_corpus={max_events})...", flush=True)
    report = BenchmarkRunner(config).run()
    print(json.dumps(
        {
            "run_id": report["run_id"],
            "headline": report.get("headline"),
            "catalog_only": report.get("catalog_only"),
            "appendix_mixed_accuracy": report.get("appendix", {}).get("mixed_overall_direction_accuracy"),
            "out_of_time_real_label": report.get("out_of_time"),
            "failed_cases": len(report.get("failed_cases", [])),
            "artifacts": report.get("artifacts"),
            "errors": len(report.get("errors", [])),
        },
        indent=2,
    ))
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
