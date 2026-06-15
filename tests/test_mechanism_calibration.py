"""Tests for Phase 3 mechanism calibration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_causal_engine.calibration.bayesian_calibrator import calibrate_posterior, domain_prior
from market_causal_engine.calibration.evaluation import evaluate_predictions
from market_causal_engine.calibration.feature_builder import (
    build_case_features,
    features_from_benchmark_record,
    features_from_claims,
)
from market_causal_engine.calibration.mechanism_model import MechanismModel, TrainingSample
from market_causal_engine.calibration.runner import calibrate_case, train_mechanism_model

ROOT = Path(__file__).resolve().parent.parent


def _synthetic_samples(n: int = 12) -> list[TrainingSample]:
    samples: list[TrainingSample] = []
    for i in range(n):
        feat = {
            "m_fundamental": 0.4 + 0.01 * i,
            "m_sentiment": 0.2,
            "m_liquidity": 0.15,
            "m_macro": 0.1,
            "m_regulatory": 0.05,
            "m_trust": 0.1,
            "max_severity": 0.8,
            "mean_confidence": 0.9,
            "trace_total": 0.3,
        }
        effect = -0.05 - 0.2 * feat["m_fundamental"] - 0.05 * feat["m_liquidity"]
        samples.append(
            TrainingSample(
                event_id=f"SYN_{i}",
                features=feat,
                effect=effect,
                domain="earnings",
                source="synthetic",
            )
        )
    return samples


def test_features_from_claims_normalize():
    claims = [
        {"mechanism": "fundamental", "severity": 0.9, "confidence": 1.0},
        {"mechanism": "liquidity", "severity": 0.6, "confidence": 0.8},
    ]
    feats = features_from_claims(claims)
    assert feats["m_fundamental"] > feats["m_liquidity"]
    assert feats["claim_count"] == 2.0


def test_benchmark_features_major_flag():
    rec = {
        "domain": "earnings",
        "scenario_id": "E1",
        "labels": {"is_major_event": True},
        "observed_outcomes": {"direction": "down", "magnitude_bucket": "large"},
    }
    feats = features_from_benchmark_record(rec)
    assert feats["is_major"] == 1.0
    assert feats["direction_sign"] == -1.0


def test_mechanism_model_fit_predict():
    model = MechanismModel().fit(_synthetic_samples())
    pred = model.predict(_synthetic_samples()[0].features)
    assert "predicted_effect" in pred
    assert pred["predicted_direction"] == "down"
    assert abs(sum(pred["mechanism_weights"].values()) - 1.0) < 0.01


def test_bayesian_posterior_normalizes():
    feats = build_case_features(
        claims=[{"mechanism": "fundamental", "severity": 0.9, "confidence": 1.0}],
        domain="earnings",
    )
    post = calibrate_posterior(feats, observed_effect=-0.25, domain="earnings")
    assert abs(sum(post["posterior_weights"].values()) - 1.0) < 0.01
    assert post["dominant_mechanism"] in post["posterior_weights"]


def test_domain_prior_sums_to_one():
    prior = domain_prior("short_report")
    assert abs(sum(prior.values()) - 1.0) < 0.01
    assert prior["trust"] >= prior["macro"]


def test_evaluate_predictions_metrics():
    metrics = evaluate_predictions(
        [
            {"outcome_effect": -0.2, "predicted_effect": -0.18, "predicted_direction": "down"},
            {"outcome_effect": 0.1, "predicted_effect": 0.05, "predicted_direction": "up"},
        ]
    )
    assert metrics["n"] == 2
    assert metrics["mae"] < 0.1


@pytest.mark.slow
def test_train_and_calibrate_nflx_case():
    model = train_mechanism_model(include_trace=False, major_only=True, save=False)
    out = calibrate_case("nflx_2022q1_earnings", model, include_trace=False, write=False)
    assert out["outcome_effect"] < -0.1
    assert out["dominant_mechanism"] in out["posterior_weights"]
    assert out["direction_match"] is True


def test_nflx_claim_features_integrate():
    claims_path = ROOT / "data" / "market" / "case_studies" / "nflx_2022q1_earnings" / "causal_claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8"))["accepted"]
    feats = build_case_features(claims=claims, domain="earnings")
    assert feats["m_fundamental"] > 0
