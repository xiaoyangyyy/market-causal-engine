"""Learned severity estimates from Phase 1 effect anchors."""

from __future__ import annotations

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.learned.store import load_learned_store


def estimate_severity(
    atom: MarketAtom | None = None,
    *,
    text: str = "",
    event_kind: str = "",
    domain: str = "earnings",
    default: float = 0.7,
) -> float:
    store = load_learned_store()
    table = store.get("severity_table", {})

    if event_kind and event_kind in table:
        base = float(table[event_kind])
    elif domain in table:
        base = float(table[domain])
    else:
        base = default

    if atom is not None:
        if atom.metadata.get("severity") is not None:
            # Blend learned prior with atom metadata (not pure heuristic).
            meta = float(atom.metadata["severity"])
            return round(0.55 * base + 0.45 * meta, 3)
        text = atom.text

    if text:
        # Mild text-length signal only (no keyword lexicon).
        norm_len = min(1.0, len(text) / 240.0)
        return round(min(0.98, base * 0.85 + norm_len * 0.15), 3)

    return round(base, 3)
