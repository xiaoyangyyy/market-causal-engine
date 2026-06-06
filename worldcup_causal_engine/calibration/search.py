"""Simple calibration search (MVP).

Search over a bounded parameter space and pick the lowest-loss configuration.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from worldcup_causal_engine.calibration.objective import LossBreakdown, evaluate_loss
from worldcup_causal_engine.calibration.observations import Dataset
from worldcup_causal_engine.scenarios import run_scenario


@dataclass(frozen=True)
class CalibrationResult:
    best_priors_override: dict[str, dict[str, float]]
    best_loss: float
    best_breakdown: LossBreakdown
    tried: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_loss": self.best_loss,
            "tried": self.tried,
            "best_priors_override": self.best_priors_override,
            "best_breakdown": {"total": self.best_breakdown.total, "items": self.best_breakdown.items},
        }


def _sample_uniform(bounds: tuple[float, float], rng: random.Random) -> float:
    lo, hi = bounds
    return lo + (hi - lo) * rng.random()


def random_search(
    *,
    scenario_path: str,
    world_id: str,
    dataset: Dataset,
    base_priors: dict[str, dict[str, float]],
    param_space: dict[str, dict[str, tuple[float, float]]],
    budget: int = 200,
    seed: int = 7,
    until: int = 120,
) -> CalibrationResult:
    """Random search over param ranges.

    param_space shape:
    {
      "official_clarification": {"rumor_reduction": (0.05,0.5)},
      "rumor_amplified": {"rumor_delta": (0.4,1.0)}
    }
    """
    rng = random.Random(seed)
    best_loss = float("inf")
    best_override: dict[str, dict[str, float]] = {}
    best_breakdown = LossBreakdown(total=float("inf"), items=[])

    for _ in range(int(budget)):
        priors_override: dict[str, dict[str, float]] = {}
        for mech, params in param_space.items():
            for k, bounds in params.items():
                priors_override.setdefault(mech, {})[k] = _sample_uniform(bounds, rng)

        result = run_scenario(
            scenario_path=scenario_path,
            world_id=world_id,
            until=until,
            priors_override=priors_override,
        )
        breakdown = evaluate_loss(result, dataset)
        if breakdown.total < best_loss:
            best_loss = breakdown.total
            best_override = priors_override
            best_breakdown = breakdown

    return CalibrationResult(
        best_priors_override=best_override,
        best_loss=float(best_loss),
        best_breakdown=best_breakdown,
        tried=int(budget),
    )

