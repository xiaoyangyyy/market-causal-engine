"""Remove pre-IPO fake earnings dates from the benchmark corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.benchmark.catalog.ipo import clean_earnings_corpus

CORPUS = Path(__file__).resolve().parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean pre-IPO / unpriceable earnings catalog events")
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--excluded", default="", help="Output path for excluded events JSONL")
    parser.add_argument("--no-enrich", action="store_true", help="Skip Yahoo label re-enrichment")
    parser.add_argument("--refresh-prices", action="store_true")
    args = parser.parse_args()

    excluded = Path(args.excluded) if args.excluded else None
    stats = clean_earnings_corpus(
        Path(args.corpus),
        excluded_path=excluded,
        re_enrich=not args.no_enrich,
        refresh_prices=args.refresh_prices,
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
