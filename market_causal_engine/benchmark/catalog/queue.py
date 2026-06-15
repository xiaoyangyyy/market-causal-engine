"""Prioritize catalog build order for maximum benchmark coverage."""

from __future__ import annotations

from pathlib import Path

from market_causal_engine.benchmark.catalog.store import manifest_path
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus


def _has_usable_atoms(event_id: str) -> bool:
    mp = manifest_path(event_id)
    if not mp.exists():
        return False
    import json

    man = json.loads(mp.read_text(encoding="utf-8"))
    return int(man.get("atom_count", 0)) > 0


def benchmark_sample_event_ids(
    *,
    corpus: str = "earnings_sp500_2016_2025",
    max_events: int = 500,
    seed: int = 42,
) -> set[str]:
    """Event ids in the stratified benchmark sample (same logic as load_corpus)."""
    events = load_corpus(corpus, max_events=max_events, seed=seed)
    return {e.event_id for e in events}


def prioritize_catalog_events(
    events: list[BenchmarkEvent],
    *,
    missing_only: bool = False,
    benchmark_first: bool = False,
    benchmark_max: int = 500,
    benchmark_seed: int = 42,
) -> list[BenchmarkEvent]:
    """Order events: benchmark sample first, then major, then rest; optionally skip built."""
    if missing_only:
        events = [e for e in events if not _has_usable_atoms(e.event_id)]

    sample_ids: set[str] = set()
    if benchmark_first:
        sample_ids = benchmark_sample_event_ids(max_events=benchmark_max, seed=benchmark_seed)

    def sort_key(ev: BenchmarkEvent) -> tuple[int, int, str]:
        in_sample = 0 if ev.event_id in sample_ids else 1
        major = 0 if ev.labels.get("is_major_event") else 1
        real = 0 if not ev.metadata.get("synthetic_labels") else 1
        return (in_sample, major, real, ev.event_id)

    return sorted(events, key=sort_key)


def catalog_coverage_stats(
    *,
    corpus: str = "earnings_sp500_2016_2025",
    benchmark_max: int = 500,
    benchmark_seed: int = 42,
) -> dict[str, int]:
    all_events = load_corpus(corpus, max_events=None)
    sample_ids = benchmark_sample_event_ids(max_events=benchmark_max, seed=benchmark_seed)
    built = sum(1 for e in all_events if _has_usable_atoms(e.event_id))
    sample_built = sum(1 for e in all_events if e.event_id in sample_ids and _has_usable_atoms(e.event_id))
    return {
        "corpus_total": len(all_events),
        "corpus_with_atoms": built,
        "benchmark_sample_size": len(sample_ids),
        "benchmark_sample_with_atoms": sample_built,
    }
