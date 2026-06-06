#!/usr/bin/env python3
"""Extract atoms.jsonl for all case studies with sources/ manifests."""

from __future__ import annotations

import json
import sys

from market_causal_engine.extraction.pipeline import build_atoms_for_case, list_extractable_cases


def main() -> int:
    results = []
    for case_id in list_extractable_cases():
        results.append(build_atoms_for_case(case_id))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    failed = [r for r in results if r.get("lookahead_passed") is False]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
