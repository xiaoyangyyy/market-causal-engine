"""Fit and export learned stack (Phase 1-3 → runtime artifacts)."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.calibration.fit_learned import fit_and_export_learned_stack
from market_causal_engine.learned.store import reload_learned_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit learned stack and export v0.2 priors")
    parser.add_argument("--trace", action="store_true", help="Include kernel trace features when fitting")
    args = parser.parse_args()

    summary = fit_and_export_learned_stack(include_trace=args.trace)
    reload_learned_store()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
