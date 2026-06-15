"""Run Phase 2 causal claim extraction for case studies."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.extraction.causal_claim_extractor import (
    extract_claims_for_case,
    run_all_case_claims,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 causal claim extraction")
    parser.add_argument("--case", default="", help="Single case study id")
    parser.add_argument("--cases", action="store_true", help="Run all case studies")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM API (fallback to heuristic)")
    parser.add_argument("--as-of", type=int, default=0, help="Look-ahead horizon in minutes")
    args = parser.parse_args()

    if args.case:
        out = extract_claims_for_case(
            args.case,
            as_of=args.as_of or None,
            use_llm=args.use_llm,
        )
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.cases:
        stats = run_all_case_claims(use_llm=args.use_llm)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
