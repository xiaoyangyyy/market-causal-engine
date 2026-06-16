"""Catalog-only direction evaluation (honest EDGAR path, no scenario router)."""

from __future__ import annotations

from typing import Any

from market_causal_engine.benchmark.catalog.claim_quality import load_catalog_claims_policy
from market_causal_engine.benchmark.catalog.claims import has_effective_catalog_claims
from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event
from market_causal_engine.benchmark.models import load_corpus
from market_causal_engine.benchmark.replay import infer_simulated_direction
from market_causal_engine.learned.store import reload_learned_store


def eval_catalog_only_metrics(*, max_events: int | None = None) -> dict[str, Any]:
    """Direction accuracy on quality-filtered catalog replay only (no router)."""
    reload_learned_store()
    policy = load_catalog_claims_policy()
    events = [
        e
        for e in load_corpus("earnings_sp500_2016_2025", max_events=None)
        if _has_usable_atoms(e.event_id)
    ]
    if max_events is not None:
        events = events[:max_events]

    ok = n = 0
    errors: list[str] = []
    for event in events:
        if not has_effective_catalog_claims(event.event_id, policy=policy):
            continue
        obs = event.observed_outcomes.get("direction")
        if obs not in ("up", "down", "neutral"):
            continue
        try:
            result = replay_catalog_feed_event(event, until=60)
            pred = infer_simulated_direction(result, event=event.to_dict())
            n += 1
            if pred == obs:
                ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{event.event_id}: {exc}")

    return {
        "catalog_only_direction_accuracy": round(ok / n, 4) if n else None,
        "catalog_only_n": n,
        "quality_eligible": n,
        "errors": len(errors),
        "inference": "domain_polarity_consensus",
        "note": "No scenario router; catalog_feed replay only.",
    }
