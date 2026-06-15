"""Run Phase 3 mechanism calibration."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.calibration.runner import calibrate_case, run_full_phase3, train_mechanism_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 mechanism calibration")
    parser.add_argument("--case", default="", help="Single case study id")
    parser.add_argument("--train", action="store_true", help="Train global mechanism model only")
    parser.add_argument("--full", action="store_true", help="Train + calibrate all cases + evaluation")
    parser.add_argument("--no-trace", action="store_true", help="Skip kernel trace features (faster)")
    parser.add_argument("--all-benchmark", action="store_true", help="Train on all benchmark events, not major-only")
    args = parser.parse_args()

    include_trace = not args.no_trace
    major_only = not args.all_benchmark

    if args.case:
        model = train_mechanism_model(include_trace=include_trace, major_only=major_only, save=True)
        out = calibrate_case(args.case, model, include_trace=include_trace)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.train:
        model = train_mechanism_model(include_trace=include_trace, major_only=major_only, save=True)
        print(json.dumps(model.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.full:
        stats = run_full_phase3(include_trace=include_trace, major_only=major_only)
        print(
            json.dumps(
                {
                    "training_samples": stats["training_samples"],
                    "cases": stats["cases"],
                    "errors": stats["errors"],
                    "in_sample_metrics": stats["in_sample_metrics"],
                    "leave_one_out": stats["leave_one_out"]["metrics"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
