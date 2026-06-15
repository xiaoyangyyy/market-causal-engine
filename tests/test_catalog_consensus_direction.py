"""Tests for catalog domain + claim polarity consensus direction."""

from __future__ import annotations

from market_causal_engine.learned.direction import (
    CATALOG_POLARITY_NET_THRESHOLD,
    _catalog_consensus_direction,
    _catalog_polarity_direction,
)


class _FakeDomainModel:
    def __init__(self, direction: str) -> None:
        self._direction = direction

    def predict(self, features: dict[str, float]) -> dict[str, str]:
        return {"predicted_direction": self._direction}


def test_catalog_polarity_direction_uses_net_threshold():
    threshold = CATALOG_POLARITY_NET_THRESHOLD
    assert _catalog_polarity_direction({"causal_claims": {"catalog_net_polarity": threshold + 0.01}}) == "up"
    assert _catalog_polarity_direction({"causal_claims": {"catalog_net_polarity": -(threshold + 0.01)}}) == "down"
    assert _catalog_polarity_direction({"causal_claims": {"catalog_net_polarity": 0.01}}) == "neutral"


def test_catalog_consensus_returns_agreed_direction():
    result = {
        "domain": "earnings",
        "replay_mode": "catalog_feed",
        "causal_claims": {"catalog_net_polarity": 0.25, "accepted": [{"polarity": 0.8}]},
        "final_risk": {"directional_pressure": 0.0, "drawdown_risk": 0.0},
        "trace": [],
    }
    pred = _catalog_consensus_direction(result, event={"domain": "earnings"}, domain_model=_FakeDomainModel("up"))
    assert pred == "up"


def test_catalog_consensus_returns_neutral_on_disagreement():
    result = {
        "domain": "earnings",
        "replay_mode": "catalog_feed",
        "causal_claims": {"catalog_net_polarity": -0.25, "accepted": [{"polarity": -0.8}]},
        "final_risk": {"directional_pressure": 0.0, "drawdown_risk": 0.0},
        "trace": [],
    }
    pred = _catalog_consensus_direction(result, event={"domain": "earnings"}, domain_model=_FakeDomainModel("up"))
    assert pred == "neutral"
