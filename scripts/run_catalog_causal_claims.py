"""Run Phase 2 causal claim extraction for catalog EDGAR events."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.benchmark.catalog.claims import (
    extract_claims_for_catalog_event,
    run_all_catalog_claims,
)
from market_causal_engine.benchmark.models import load_corpus
from market_causal_engine.extraction.llm_config import load_llm_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 catalog causal claim extraction")
    parser.add_argument("--event", default="", help="Single catalog event_id")
    parser.add_argument("--all", action="store_true", help="Run all catalog events with atoms")
    parser.add_argument("--benchmark-sample", action="store_true", help="Limit to benchmark sample (~500)")
    parser.add_argument("--missing-only", action="store_true", help="Skip events that already have claims")
    parser.add_argument("--heuristic-only", action="store_true", help="Only events with heuristic (non-LLM) claims")
    parser.add_argument("--atom-fallback-only", action="store_true", help="Only LLM atom-fallback events (upgrade pass)")
    parser.add_argument("--quality-refresh", action="store_true", help="Re-extract events needing claim quality refresh")
    parser.add_argument("--force", action="store_true", help="Re-extract all events (overrides --missing-only)")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM API (event-level batch)")
    parser.add_argument("--api-key", default="", help="API key (or set OPENAI_API_KEY / ZHISUAN_API_KEY)")
    parser.add_argument("--base-url", default="", help="OpenAI-compatible base URL")
    parser.add_argument("--model", default="", help="LLM model name")
    parser.add_argument("--max-events", type=int, default=0, help="Limit batch size (0 = no limit)")
    args = parser.parse_args()

    if args.heuristic_only and args.atom_fallback_only:
        print(json.dumps({"error": "Use only one of --heuristic-only or --atom-fallback-only"}, indent=2))
        return 1
    if sum(bool(x) for x in (args.heuristic_only, args.atom_fallback_only, args.quality_refresh)) > 1:
        print(json.dumps({"error": "Use only one filter: --heuristic-only, --atom-fallback-only, --quality-refresh"}, indent=2))
        return 1

    llm = load_llm_config(
        api_key=args.api_key or None,
        base_url=args.base_url or None,
        model=args.model or None,
    )

    if args.event:
        events = load_corpus("earnings_sp500_2016_2025", max_events=None)
        match = next((e for e in events if e.event_id == args.event), None)
        if match is None:
            print(json.dumps({"error": f"Unknown event_id: {args.event}"}, indent=2))
            return 1
        out = extract_claims_for_catalog_event(match, use_llm=args.use_llm, llm=llm)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.all:
        stats = run_all_catalog_claims(
            use_llm=args.use_llm,
            llm=llm if args.use_llm else None,
            max_events=args.max_events or None,
            missing_only=args.missing_only and not args.force,
            heuristic_only=args.heuristic_only,
            atom_fallback_only=args.atom_fallback_only,
            quality_refresh_only=args.quality_refresh,
            benchmark_sample=args.benchmark_sample,
        )
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
