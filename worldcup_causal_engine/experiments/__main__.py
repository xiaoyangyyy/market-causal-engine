"""CLI: python -m worldcup_causal_engine.experiments"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from worldcup_causal_engine.experiments.ablation import run_ablation
from worldcup_causal_engine.experiments.llm_baseline import run_llm_baseline
from worldcup_causal_engine.experiments.runner import export_report, run_pressure_test
from worldcup_causal_engine.experiments.sensitivity import run_sensitivity_grid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="World Cup causal engine — Phase 4 experiments")
    parser.add_argument(
        "--experiment",
        required=True,
        choices=["pressure_test", "ablation", "sensitivity", "llm_baseline"],
    )
    parser.add_argument("--scenarios", default="S1,S2,S3")
    parser.add_argument("--worlds", default="W0,W1,W2,W3,W4,W5")
    parser.add_argument("--until", type=int, default=120)
    parser.add_argument("--output", default=None)
    parser.add_argument("--runs", type=int, default=5, help="LLM baseline runs per world")
    parser.add_argument("--use-api", action="store_true", help="Use OpenAI API if key set")
    args = parser.parse_args(argv)

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    if args.experiment == "pressure_test":
        worlds = [w.strip() for w in args.worlds.split(",") if w.strip()]
        out = args.output or "results/experiment_1"
        results = run_pressure_test(scenarios, worlds, args.until, out)
        summary = export_report(results, Path(out) / "summary.json")
        print(f"Completed {summary['runs']} runs → {out}", file=sys.stderr)

    elif args.experiment == "ablation":
        out = args.output or "results/experiment_2"
        summary = run_ablation(scenarios, until=args.until, output_dir=out)
        print(f"Ablation {summary['runs']} runs → {out}", file=sys.stderr)

    elif args.experiment == "sensitivity":
        out = args.output or "results/experiment_sensitivity"
        summary = run_sensitivity_grid(scenario=scenarios[0], output_dir=out)
        print(f"Sensitivity {summary['runs']} runs, path_stable={summary['path_stable']}", file=sys.stderr)

    elif args.experiment == "llm_baseline":
        out = args.output or "results/experiment_3"
        for sc in scenarios[:2]:
            run_llm_baseline(sc, runs=args.runs, output_dir=out, use_api=args.use_api)
        print(f"LLM baseline → {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
