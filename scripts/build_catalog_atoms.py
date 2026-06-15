"""Batch-build per-ticker EDGAR atoms for earnings catalog events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.benchmark.catalog.fetch import build_atoms_batch, build_atoms_for_event
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus

CORPUS = Path(__file__).resolve().parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build EDGAR atoms for earnings catalog events")
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--event-id", default="", help="Build a single event by id")
    parser.add_argument("--max", type=int, default=0, help="Max events to fetch (0 = all)")
    parser.add_argument("--major-only", action="store_true", help="Only |return|>=3% events")
    parser.add_argument("--real-labels-only", action="store_true", help="Skip synthetic-label events")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--rebuild-empty",
        action="store_true",
        help="Re-fetch events whose catalog manifest has atom_count=0",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Skip events that already have usable catalog atoms",
    )
    parser.add_argument(
        "--benchmark-sample",
        action="store_true",
        help="Prioritize events in the benchmark stratified 500-event sample",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Print catalog coverage stats and exit",
    )
    args = parser.parse_args()

    if args.coverage:
        from market_causal_engine.benchmark.catalog.queue import catalog_coverage_stats

        print(json.dumps(catalog_coverage_stats(), indent=2, ensure_ascii=False))
        return 0

    if args.event_id:
        events = load_corpus(Path(args.corpus).stem.replace(".jsonl", ""), max_events=None)
        match = [e for e in events if e.event_id == args.event_id]
        if not match:
            # load from file directly
            for line in Path(args.corpus).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("event_id") == args.event_id:
                        match = [BenchmarkEvent.from_dict(rec)]
                        break
        if not match:
            print(json.dumps({"error": f"event not found: {args.event_id}"}))
            return 1
        report = build_atoms_for_event(match[0], overwrite=args.overwrite)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    corpus_name = Path(args.corpus).stem
    events = load_corpus(corpus_name, max_events=None)
    if args.real_labels_only:
        events = [e for e in events if not e.metadata.get("synthetic_labels")]

    if args.rebuild_empty:
        from market_causal_engine.benchmark.catalog.store import manifest_path
        import json as _json

        empty_ids: set[str] = set()
        for ev in events:
            mp = manifest_path(ev.event_id)
            if not mp.exists():
                continue
            man = _json.loads(mp.read_text(encoding="utf-8"))
            if int(man.get("atom_count", 0)) == 0:
                empty_ids.add(ev.event_id)
        events = [e for e in events if e.event_id in empty_ids]
        args.overwrite = True

    from market_causal_engine.benchmark.catalog.queue import prioritize_catalog_events

    events = prioritize_catalog_events(
        events,
        missing_only=args.missing_only,
        benchmark_first=args.benchmark_sample,
    )

    stats = build_atoms_batch(
        events,
        overwrite=args.overwrite,
        max_events=args.max or None,
        major_only=args.major_only,
    )
    stats["coverage"] = __import__(
        "market_causal_engine.benchmark.catalog.queue", fromlist=["catalog_coverage_stats"]
    ).catalog_coverage_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
