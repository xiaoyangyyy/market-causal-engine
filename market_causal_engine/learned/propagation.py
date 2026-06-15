"""Learned scaling for mechanism commit patches."""

from __future__ import annotations

from typing import Any

from market_causal_engine.analysis import category_for_kind
from market_causal_engine.learned.store import load_learned_store


def scale_patch(
    patch: dict[str, float],
    *,
    event_kind: str,
    domain: str = "earnings",
    learned: dict[str, Any] | None = None,
) -> dict[str, float]:
    store = learned or load_learned_store()
    kind_scale = float(store.get("kind_scales", {}).get(event_kind, store.get("kind_scales", {}).get("*", 1.0)))
    kind_scale = max(0.5, min(2.5, kind_scale))

    posteriors = store.get("domain_posteriors", {}).get(domain, {})
    category = category_for_kind(event_kind)
    if posteriors and category:
        mean_w = sum(float(v) for v in posteriors.values()) / max(len(posteriors), 1)
        rel = float(posteriors.get(category, mean_w)) / max(mean_w, 1e-6)
        rel = max(0.75, min(1.35, rel))
    else:
        rel = 1.0

    scale = kind_scale * rel
    return {k: round(v * scale, 6) for k, v in patch.items()}
