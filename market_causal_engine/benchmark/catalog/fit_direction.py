"""Fit catalog-feed direction model from events with EDGAR atoms."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from market_causal_engine.benchmark.catalog.atoms import (
    apply_catalog_evidence_scale,
    enrich_catalog_atoms,
)
from market_causal_engine.benchmark.catalog.direction import (
    fit_catalog_direction_params,
    save_catalog_direction_model,
    training_sample_from_event,
    _direction_match,
)
from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event
from market_causal_engine.benchmark.catalog.severity import catalog_replay_severity_scale
from market_causal_engine.benchmark.catalog.store import atoms_path
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus
from market_causal_engine.evidence import load_atoms


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def collect_catalog_direction_samples(
    events: list[BenchmarkEvent] | None = None,
    *,
    max_events: int | None = None,
) -> list[tuple[dict[str, float], str]]:
    if events is None:
        events = load_corpus("earnings_sp500_2016_2025", max_events=None)

    samples: list[tuple[dict[str, float], str]] = []
    for event in events:
        if event.metadata.get("synthetic_labels"):
            continue
        if not _has_usable_atoms(event.event_id):
            continue
        obs = event.observed_outcomes.get("direction")
        if obs not in ("up", "down", "neutral"):
            continue
        try:
            result = replay_catalog_feed_event(event, until=60)
            atoms = enrich_catalog_atoms(load_atoms(atoms_path(event.event_id)))
            samples.append(training_sample_from_event(result, observed_direction=str(obs), atoms=atoms))
        except Exception:  # noqa: BLE001
            continue
        if max_events is not None and len(samples) >= max_events:
            break
    return samples


def fit_catalog_direction_model(
    *,
    max_events: int | None = None,
) -> dict[str, Any]:
    samples = collect_catalog_direction_samples(max_events=max_events)
    if len(samples) < 12:
        raise ValueError(f"Insufficient catalog training samples: {len(samples)} (need >= 12)")

    model = fit_catalog_direction_params(samples)
    save_catalog_direction_model(model)

    correct = sum(1 for feats, obs in samples if _direction_match(obs, model.predict_direction(feats)))
    return {
        "computed_at": _utc_now(),
        "n_samples": len(samples),
        "training_accuracy": round(correct / len(samples), 4),
        "params": model.params,
        "artifact": str(save_catalog_direction_model(model)),
    }
