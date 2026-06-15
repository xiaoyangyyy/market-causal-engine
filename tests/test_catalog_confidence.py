"""Tests for catalog confidence gating."""

from __future__ import annotations

from market_causal_engine.benchmark.catalog.confidence import catalog_signal_strength, should_use_catalog_feed


def test_mild_kernel_low_confidence():
    strength = catalog_signal_strength(
        {"final_risk": {"directional_pressure": 0.04, "drawdown_risk": 0.08}},
        atoms=[],
    )
    assert strength < 0.22
    assert not should_use_catalog_feed(
        {"final_risk": {"directional_pressure": 0.04, "drawdown_risk": 0.08}},
        atoms=[],
    )


def test_high_pressure_high_confidence():
    result = {"final_risk": {"directional_pressure": 0.42, "drawdown_risk": 0.31}}
    assert catalog_signal_strength(result, atoms=[]) >= 0.22
    assert should_use_catalog_feed(result, atoms=[])
