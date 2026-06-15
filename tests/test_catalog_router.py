"""Tests for Phase 4 catalog router."""

from __future__ import annotations

from market_causal_engine.benchmark.catalog.router import CatalogRouterModel, build_router_features
from market_causal_engine.calibration.mechanism_model import TrainingSample


def test_router_prefers_catalog_on_high_delta():
    cat = {
        "domain": "earnings",
        "final_risk": {"directional_pressure": 0.35, "drawdown_risk": 0.30},
        "trace": [{"action": "commit", "patch": {"directional_pressure_score": 0.2}}],
        "_predicted_effect": -0.8,
    }
    scn = {
        "domain": "earnings",
        "final_risk": {"directional_pressure": 0.05, "drawdown_risk": 0.08},
        "trace": [],
        "_predicted_effect": 0.1,
    }
    feats = build_router_features(cat, scn)
    samples = [
        TrainingSample(event_id=f"e{i}", features=feats, effect=1.0, domain="earnings", source="router")
        for i in range(25)
    ]
    model = CatalogRouterModel().fit(samples)
    assert model.prefer_catalog(feats) is True
