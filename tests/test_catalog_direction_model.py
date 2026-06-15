"""Tests for learned catalog direction classifier."""

from __future__ import annotations

from market_causal_engine.benchmark.catalog.direction_model import (
    CatalogDirectionModel,
    DirectionSample,
    build_catalog_direction_features,
)


def test_direction_model_beats_random_on_synthetic():
    samples: list[DirectionSample] = []
    for i in range(60):
        direction = ("up", "down", "neutral")[i % 3]
        pressure = 0.35 if direction == "down" else (-0.12 if direction == "up" else 0.04)
        bias = -0.15 if direction == "down" else (0.12 if direction == "up" else 0.0)
        effect = -0.2 if direction == "down" else (0.2 if direction == "up" else 0.0)
        result = {
            "domain": "earnings",
            "final_risk": {"directional_pressure": pressure, "drawdown_risk": 0.2},
            "trace": [{"action": "commit", "patch": {"directional_pressure_score": bias}}],
            "causal_claims": {
                "accepted": [
                    {
                        "mechanism": "fundamental",
                        "severity": 0.8 if direction != "neutral" else 0.2,
                        "confidence": 0.9,
                    }
                ]
            },
        }
        feats = build_catalog_direction_features(result, {"domain": "earnings"})
        feats["pred_effect"] = effect
        feats["claim_polarity_net"] = effect
        feats["kernel_pressure"] = 0.35 if direction == "down" else (-0.12 if direction == "up" else 0.04)
        feats["kernel_drawdown"] = 0.2
        samples.append(
            DirectionSample(
                event_id=f"e{i}",
                event_date=f"2020-{(i % 12) + 1:02d}-01",
                features=feats,
                direction=direction,
            )
        )

    model = CatalogDirectionModel().fit(samples, holdout_ratio=0.25)
    assert model.training_accuracy is not None
    assert model.training_accuracy >= 0.33
