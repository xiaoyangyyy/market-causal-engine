"""CLI for Market Event Causal Engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.constants import DOMAIN_REGISTRY, SCENARIO_FILES, WORLD_DESCRIPTIONS, WORLD_IDS
from market_causal_engine.reverse import analyze_result, diff_results
from market_causal_engine.scenarios import run_counterfactual_suite, run_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Market Event Causal Engine — trace-first event-impact forensics "
            "(not a buy/sell predictor)"
        )
    )
    parser.add_argument("--scenario", help="Path to scenario JSON file")
    parser.add_argument(
        "--scenario-id",
        choices=list(SCENARIO_FILES.keys()),
        help="Built-in scenario shorthand (E1/E2, S1/S2, X1/X2; M1–M4 legacy aliases)",
    )
    parser.add_argument(
        "--list-domains",
        action="store_true",
        help="List engine product lines (earnings / short_report / macro)",
    )
    parser.add_argument(
        "--list-mvp",
        action="store_true",
        help="Alias for --list-domains",
    )
    parser.add_argument(
        "--world",
        default="W0",
        choices=WORLD_IDS,
        help="Counterfactual world (W0=baseline)",
    )
    parser.add_argument("--until", type=int, default=30, help="Simulation end time (session steps)")
    parser.add_argument("--output", help="Write result JSON to this file")
    parser.add_argument("--priors", help="Path to mechanism priors JSON")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print reverse-debugger explanation to stderr",
    )
    parser.add_argument(
        "--diff-against",
        metavar="WORLD",
        help="Compare trace against another world (e.g. W0)",
    )
    parser.add_argument(
        "--counterfactual-suite",
        action="store_true",
        help="Run W0–W7 and print counterfactual diffs",
    )
    parser.add_argument("--feed", help="Path to JSONL atom feed")
    parser.add_argument("--ticker", default="ACME", help="Ticker for feed cluster keys")
    parser.add_argument("--ledger-output", help="Write evidence ledger JSON")
    parser.add_argument(
        "--case-study",
        metavar="CASE_ID",
        help="Run historical case study by id (e.g. nflx_2022q1_earnings)",
    )
    parser.add_argument(
        "--list-case-studies",
        action="store_true",
        help="List available historical case studies",
    )
    parser.add_argument(
        "--as-of",
        type=int,
        help="Case study simulation horizon in minutes (look-ahead cutoff)",
    )
    parser.add_argument(
        "--validate-lookahead",
        action="store_true",
        help="With --case-study: only audit atom timestamps, do not run kernel",
    )
    parser.add_argument(
        "--case-counterfactual",
        action="store_true",
        help="With --case-study: run W0/W1/W3/W6 counterfactual comparison",
    )
    parser.add_argument(
        "--extract-atoms",
        metavar="CASE_ID",
        help="Run SEC/news extraction pipeline and write atoms.jsonl",
    )
    parser.add_argument(
        "--extract-all",
        action="store_true",
        help="Extract atoms for all cases with sources/ manifests",
    )
    parser.add_argument(
        "--fetch-edgar",
        metavar="CASE_ID",
        help="Download SEC EDGAR filing(s) into case sources/ (requires network)",
    )
    parser.add_argument(
        "--fetch-edgar-all",
        action="store_true",
        help="Fetch EDGAR sources for all cases with edgar config in sources.json",
    )
    parser.add_argument(
        "--fetch-and-extract",
        metavar="CASE_ID",
        help="Fetch EDGAR then extract atoms for one case",
    )
    parser.add_argument(
        "--fetch-macro",
        metavar="CASE_ID",
        help="Download FOMC/BLS macro release into case sources/ (requires network)",
    )
    parser.add_argument(
        "--fetch-macro-all",
        action="store_true",
        help="Fetch macro sources for all cases with macro_fetch config",
    )
    parser.add_argument(
        "--fetch-and-extract-macro",
        metavar="CASE_ID",
        help="Fetch macro release then extract atoms for one case",
    )
    parser.add_argument(
        "--no-strict-lookahead",
        action="store_true",
        help="Disable strict look-ahead filtering (debug only)",
    )

    args = parser.parse_args(argv)

    if args.list_mvp or args.list_domains:
        print(json.dumps(DOMAIN_REGISTRY, indent=2, ensure_ascii=False))
        return 0

    if args.list_case_studies:
        from market_causal_engine.case_study import list_case_studies

        print(json.dumps(list_case_studies(), indent=2, ensure_ascii=False))
        return 0

    if args.extract_all or args.extract_atoms:
        from market_causal_engine.extraction.pipeline import build_atoms_for_case, list_extractable_cases

        cases = list_extractable_cases() if args.extract_all else [args.extract_atoms]
        results = []
        for cid in cases:
            results.append(build_atoms_for_case(cid, as_of=args.as_of))
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    if args.fetch_edgar_all or args.fetch_edgar:
        from market_causal_engine.extraction.edgar_fetch import fetch_all_edgar_cases, fetch_edgar_for_case

        if args.fetch_edgar_all:
            results = fetch_all_edgar_cases()
        else:
            results = [fetch_edgar_for_case(args.fetch_edgar)]
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    if args.fetch_and_extract:
        from market_causal_engine.extraction.pipeline import build_atoms_for_case

        result = build_atoms_for_case(args.fetch_and_extract, as_of=args.as_of, fetch_edgar=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.fetch_macro_all or args.fetch_macro:
        from market_causal_engine.extraction.macro_fetch import fetch_all_macro_cases, fetch_macro_for_case

        if args.fetch_macro_all:
            results = fetch_all_macro_cases()
        else:
            results = [fetch_macro_for_case(args.fetch_macro)]
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    if args.fetch_and_extract_macro:
        from market_causal_engine.extraction.macro_fetch import fetch_macro_for_case
        from market_causal_engine.extraction.pipeline import build_atoms_for_case

        fetch_macro_for_case(args.fetch_and_extract_macro)
        result = build_atoms_for_case(args.fetch_and_extract_macro, as_of=args.as_of)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.case_study:
        from market_causal_engine.case_study import run_case_counterfactual, run_case_study

        horizon = args.as_of or args.until
        if args.case_counterfactual:
            out = run_case_counterfactual(args.case_study, until=horizon)
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        result = run_case_study(
            args.case_study,
            world_id=args.world,
            until=horizon,
            as_of=args.as_of,
            strict_lookahead=not args.no_strict_lookahead,
            validate_only=args.validate_lookahead,
            ledger_output=args.ledger_output,
        )

        if args.diff_against:
            baseline = run_case_study(
                args.case_study,
                world_id=args.diff_against,
                until=horizon,
                as_of=args.as_of,
                strict_lookahead=not args.no_strict_lookahead,
            )
            result["counterfactual_diff"] = diff_results(baseline, result)

        if args.explain and not args.validate_lookahead:
            dbg = analyze_result(result)
            print(dbg.explain(result.get("scenario_id", ""), result.get("world_id", "")), file=sys.stderr)
            cs = result.get("case_study", {})
            if cs:
                print(f"\nCase study: {json.dumps(cs, ensure_ascii=False)}", file=sys.stderr)
            audit = result.get("lookahead_audit", {})
            print(
                f"\nLook-ahead audit: {audit.get('accepted_count')} accepted, "
                f"{audit.get('rejected_count')} rejected",
                file=sys.stderr,
            )

        out_json = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(out_json, encoding="utf-8")
        else:
            print(out_json)
        return 0

    root = Path(__file__).resolve().parent.parent
    if args.scenario_id:
        scenario_path = root / "data" / "market" / "scenarios" / SCENARIO_FILES[args.scenario_id]
    elif args.scenario:
        scenario_path = Path(args.scenario)
    else:
        parser.error("Provide --scenario or --scenario-id")

    if args.counterfactual_suite:
        suite = run_counterfactual_suite(scenario_path, until=args.until)
        print(json.dumps(suite, indent=2, ensure_ascii=False))
        return 0

    result = run_scenario(
        scenario_path,
        world_id=args.world,
        until=args.until,
        priors_path=args.priors,
        feed_path=args.feed,
        ticker=args.ticker,
        ledger_output=args.ledger_output,
    )

    if args.diff_against:
        baseline = run_scenario(scenario_path, world_id=args.diff_against, until=args.until)
        diff = diff_results(baseline, result)
        result["counterfactual_diff"] = diff

    if args.explain:
        dbg = analyze_result(result)
        print(dbg.explain(result.get("scenario_id", ""), result.get("world_id", "")), file=sys.stderr)
        print(f"\nMarket regime: {result.get('market_regime')}", file=sys.stderr)
        mvp_out = result.get("mvp_output", {})
        if mvp_out:
            print(f"MVP ({result.get('mvp')}): {json.dumps(mvp_out, ensure_ascii=False)}", file=sys.stderr)
        if args.world in WORLD_DESCRIPTIONS:
            print(f"World: {WORLD_DESCRIPTIONS[args.world]}", file=sys.stderr)

    out_json = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out_json, encoding="utf-8")
    else:
        print(out_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
