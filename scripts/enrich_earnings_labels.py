"""Enrich earnings benchmark corpus with real Yahoo daily return labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.benchmark.labels import enrich_earnings_corpus

CORPUS = Path(__file__).resolve().parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich earnings benchmark with real AH/session labels")
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--refresh", action="store_true", help="Refresh Yahoo price cache")
    parser.add_argument("--dry-run", action="store_true", help="Stats only on first 20 events")
    args = parser.parse_args()

    path = Path(args.corpus)
    if args.dry_run:
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()][:20]
        from market_causal_engine.benchmark.labels import enrich_event_record, fetch_ticker_daily_bars

        sample = []
        for r in lines:
            bars = fetch_ticker_daily_bars(r["ticker"])
            sample.append(enrich_event_record(r, bars=bars))
        print(json.dumps(sample[:3], indent=2, ensure_ascii=False))
        return 0

    stats = enrich_earnings_corpus(path, refresh_prices=args.refresh)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
