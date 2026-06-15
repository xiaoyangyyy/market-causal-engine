"""Run Phase 1 market counterfactual estimation."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.counterfactuals.estimate import estimate_outcome_causal
from market_causal_engine.counterfactuals.runner import (
    run_benchmark_counterfactuals,
    run_case_counterfactuals,
    run_full_phase1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 outcome causal counterfactuals")
    parser.add_argument("--ticker", default="", help="Single ticker estimate")
    parser.add_argument("--event-date", default="", help="Event date YYYY-MM-DD")
    parser.add_argument("--method", default="auto", choices=["auto", "abnormal_return", "factor_model", "synthetic_control"])
    parser.add_argument("--cases", action="store_true", help="Run all case studies")
    parser.add_argument("--benchmark", action="store_true", help="Run earnings benchmark corpus")
    parser.add_argument("--full", action="store_true", help="Cases (SC) + benchmark (AR) full Phase 1")
    parser.add_argument("--corpus", default="earnings_sp500_2016_2025")
    parser.add_argument("--major-only", action="store_true")
    parser.add_argument("--max-events", type=int, default=0)
    args = parser.parse_args()

    if args.ticker and args.event_date:
        out = estimate_outcome_causal(args.ticker, args.event_date, method=args.method)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.full:
        stats = run_full_phase1()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    if args.cases:
        stats = run_case_counterfactuals(method="synthetic_control")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    if args.benchmark:
        stats = run_benchmark_counterfactuals(
            args.corpus,
            method=args.method if args.method != "auto" else "abnormal_return",
            major_only=args.major_only,
            max_events=args.max_events or None,
        )
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
