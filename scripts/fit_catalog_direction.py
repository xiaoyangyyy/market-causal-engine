"""Fit catalog-feed direction model from EDGAR atom replays."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.benchmark.catalog.fit_direction import fit_catalog_direction_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit catalog direction model")
    parser.add_argument("--max", type=int, default=0, help="Max training events (0 = all with atoms)")
    args = parser.parse_args()

    summary = fit_catalog_direction_model(
        max_events=args.max or None,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
