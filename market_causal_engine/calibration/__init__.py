"""Calibration: kernel impact mapping + learned mechanism weights (Phase 3)."""

from market_causal_engine.calibration.bayesian_calibrator import calibrate_posterior, domain_prior
from market_causal_engine.calibration.evaluation import evaluate_predictions, leave_one_out_case_eval
from market_causal_engine.calibration.feature_builder import (
    build_case_features,
    features_from_benchmark_record,
    features_from_claims,
)
from market_causal_engine.calibration.impact import (
    attach_calibration,
    calibrate_final_risk,
    estimate_return_pct,
    load_impact_anchors,
)
from market_causal_engine.calibration.mechanism_model import (
    MechanismModel,
    TrainingSample,
    default_model_path,
    load_model,
    save_model,
)
from market_causal_engine.calibration.runner import (
    build_training_samples,
    calibrate_case,
    run_full_phase3,
    train_mechanism_model,
)

__all__ = [
    "MechanismModel",
    "TrainingSample",
    "attach_calibration",
    "build_case_features",
    "build_training_samples",
    "calibrate_case",
    "calibrate_final_risk",
    "calibrate_posterior",
    "default_model_path",
    "domain_prior",
    "estimate_return_pct",
    "evaluate_predictions",
    "features_from_benchmark_record",
    "features_from_claims",
    "leave_one_out_case_eval",
    "load_impact_anchors",
    "load_model",
    "run_full_phase3",
    "save_model",
    "train_mechanism_model",
]
