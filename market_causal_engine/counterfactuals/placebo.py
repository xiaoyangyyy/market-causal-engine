"""Placebo inference: rank event effect vs pseudo-event dates."""

from __future__ import annotations

import random
from typing import Any, Callable


def placebo_dates(
    pre_dates: list[str],
    *,
    n_placebos: int = 20,
    min_gap: int = 10,
    seed: int = 42,
) -> list[str]:
    """Sample pseudo-event dates from pre-estimation window."""
    if len(pre_dates) < min_gap * 2:
        return []
    rng = random.Random(seed)
    candidates = pre_dates[min_gap:-min_gap]
    if not candidates:
        return []

    chosen: list[str] = []
    attempts = 0
    while len(chosen) < n_placebos and attempts < n_placebos * 20:
        attempts += 1
        d = rng.choice(candidates)
        if all(abs(pre_dates.index(d) - pre_dates.index(c)) >= min_gap for c in chosen):
            chosen.append(d)
    return sorted(chosen)


def compute_placebo_rank(
    actual_effect: float,
    placebo_effects: list[float],
) -> float | None:
    """Fraction of placebo |effects| strictly smaller than |actual|."""
    if not placebo_effects:
        return None
    actual_abs = abs(actual_effect)
    smaller = sum(1 for e in placebo_effects if abs(e) < actual_abs)
    return round(smaller / len(placebo_effects), 4)


def run_placebo_suite(
    placebo_event_dates: list[str],
    effect_fn: Callable[[str], float],
) -> dict[str, Any]:
    effects: list[float] = []
    errors: list[str] = []
    for d in placebo_event_dates:
        try:
            effects.append(effect_fn(d))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{d}: {exc}")
    return {"placebo_effects": effects, "placebo_errors": errors}
