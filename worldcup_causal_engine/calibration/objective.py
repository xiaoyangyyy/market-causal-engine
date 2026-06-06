"""Calibration objective: compare kernel outputs against observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from worldcup_causal_engine.calibration.observations import Dataset, Observation


@dataclass(frozen=True)
class LossBreakdown:
    total: float
    items: list[dict[str, Any]]


def _get_predicted_value(result: dict[str, Any], key: str) -> float | None:
    risk = result.get("final_risk", {})
    if key in ("verbal_conflict", "scuffle", "riot", "panic"):
        return float(risk.get(key, 0.0))

    state = result.get("final_state", {})
    state_map = {
        "rumor_volume_index": "rumor_volume",
        "media_outrage_index": "outrage_frame",
    }
    if key in state_map and state_map[key] in state:
        return float(state[state_map[key]])
    return None


def evaluate_loss(result: dict[str, Any], dataset: Dataset) -> LossBreakdown:
    """MVP: compare only final risk observations.

    Extend later to time-bucketed state series via causal_ledger snapshots.
    """
    items: list[dict[str, Any]] = []
    total = 0.0
    for o in dataset.observations:
        if o.time_bucket != "final":
            continue
        pred = _get_predicted_value(result, o.key)
        if pred is None:
            continue
        err = (pred - o.value) ** 2
        werr = o.weight * err
        total += werr
        items.append(
            {
                "key": o.key,
                "pred": pred,
                "obs": o.value,
                "weight": o.weight,
                "squared_error": err,
                "weighted_error": werr,
            }
        )
    return LossBreakdown(total=total, items=items)

