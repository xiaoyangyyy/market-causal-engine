"""Market econometric counterfactuals (Phase 1)."""

from market_causal_engine.counterfactuals.estimate import estimate_outcome_causal
from market_causal_engine.counterfactuals.outcome_layer import (
    attach_outcome_causal,
    build_event_card,
    build_outcome_card,
    event_study_metrics,
)
from market_causal_engine.counterfactuals.runner import (
    run_benchmark_counterfactuals,
    run_case_counterfactuals,
    run_full_phase1,
)

__all__ = [
    "attach_outcome_causal",
    "build_event_card",
    "build_outcome_card",
    "estimate_outcome_causal",
    "event_study_metrics",
    "run_benchmark_counterfactuals",
    "run_case_counterfactuals",
    "run_full_phase1",
    "attach_car_ablation",
    "run_car_ablation",
    "should_run_car_ablation",
]


def __getattr__(name: str):
    if name in {"attach_car_ablation", "run_car_ablation", "should_run_car_ablation"}:
        from market_causal_engine.counterfactuals import car_ablation as mod

        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
