"""CLI entry point for calibration search (Phase 8 MVP)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_causal_engine.calibration.observations import Dataset
from worldcup_causal_engine.calibration.search import random_search
from worldcup_causal_engine.scenarios import load_priors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 8: post-hoc calibration (MVP random search)")
    p.add_argument("--scenario", required=True, help="Scenario JSON path")
    p.add_argument("--world", default="W0", help="World id")
    p.add_argument("--observations", required=True, help="Observations JSONL path")
    p.add_argument("--budget", type=int, default=200)
    p.add_argument("--until", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--output", help="Write calibration result JSON")
    args = p.parse_args(argv)

    dataset = Dataset.load_jsonl(args.observations)
    base_priors = load_priors()

    # MVP default param space (small)
    param_space = {
        "rumor_amplified": {"rumor_delta": (0.4, 1.0)},
        "official_clarification": {"rumor_reduction": (0.05, 0.5)},
    }
    out = random_search(
        scenario_path=args.scenario,
        world_id=args.world,
        dataset=dataset,
        base_priors=base_priors,
        param_space=param_space,
        budget=args.budget,
        seed=args.seed,
        until=args.until,
    )

    payload = out.to_dict()
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

