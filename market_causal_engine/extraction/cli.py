"""CLI for atom extraction pipeline."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.extraction.edgar_fetch import fetch_edgar_for_case, list_edgar_fetchable_cases
from market_causal_engine.extraction.pipeline import build_atoms_for_case, extract_from_case, list_extractable_cases
from market_causal_engine.case_study import run_case_study


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract market evidence atoms from SEC/news sources")
    parser.add_argument("--case", help="Case study id")
    parser.add_argument("--list", action="store_true", help="List cases with sources/ manifests")
    parser.add_argument("--list-edgar", action="store_true", help="List cases with EDGAR fetch config")
    parser.add_argument("--dry-run", action="store_true", help="Extract but do not write atoms.jsonl")
    parser.add_argument("--as-of", type=int, help="Look-ahead validation horizon (minutes)")
    parser.add_argument("--fetch-edgar", action="store_true", help="Fetch SEC EDGAR before extract")
    parser.add_argument("--run-case", action="store_true", help="After extract, run case study replay")
    parser.add_argument("--preview", action="store_true", help="Print extracted atoms JSON")

    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps(list_extractable_cases(), indent=2))
        return 0

    if args.list_edgar:
        print(json.dumps(list_edgar_fetchable_cases(), indent=2))
        return 0

    if not args.case:
        parser.error("--case is required unless using --list or --list-edgar")

    if args.preview or args.dry_run:
        atoms, report = extract_from_case(args.case)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        for atom in atoms:
            print(json.dumps(atom.to_dict(), ensure_ascii=False))
        return 0

    result = build_atoms_for_case(
        args.case,
        as_of=args.as_of,
        write=not args.dry_run,
        fetch_edgar=args.fetch_edgar,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.run_case:
        replay = run_case_study(args.case, as_of=args.as_of)
        summary = {
            "direction_match": replay.get("case_study", {}).get("direction_match"),
            "calibrated_impact": replay.get("calibrated_impact"),
            "dominant_path": replay.get("dominant_causal_path"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
