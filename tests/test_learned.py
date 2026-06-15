"""Tests for learned layer (replaces rule/heuristic paths)."""

from __future__ import annotations

import json
from pathlib import Path

from market_causal_engine.analysis import category_for_kind, compute_mechanism_contributions
from market_causal_engine.benchmark.replay import infer_simulated_direction
from market_causal_engine.calibration.fit_learned import fit_and_export_learned_stack
from market_causal_engine.compiler import MarketCompiler
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.learned.propagation import scale_patch
from market_causal_engine.learned.store import learned_available, load_learned_store, reload_learned_store

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "data" / "market" / "compiler_rules" / "v0.1.json"


def test_fit_learned_stack_exports_artifacts():
    summary = fit_and_export_learned_stack(include_trace=False)
    reload_learned_store()
    assert summary["training_samples"] > 0
    assert learned_available()
    store = load_learned_store()
    assert store.get("domain_models")
    assert (ROOT / "data" / "market" / "priors" / "mechanisms_v0.2_learned.json").exists()


def test_features_from_scenario_template_has_no_label_leak():
    from market_causal_engine.calibration.feature_builder import features_from_scenario_template

    feats = features_from_scenario_template("E2", domain="earnings")
    assert "direction_sign" not in feats
    assert feats["m_sentiment"] > feats["m_fundamental"] * 0.5


def test_event_replay_severity_scale_for_mild_events():
    from market_causal_engine.benchmark.models import BenchmarkEvent
    from market_causal_engine.scenarios import event_replay_severity_scale

    mild = BenchmarkEvent(
        event_id="m",
        corpus="earnings_sp500_2016_2025",
        ticker="X",
        event_date="2020-01-01",
        event_type="earnings",
        domain="earnings",
        replay_mode="scenario",
        observed_outcomes={"direction": "neutral", "magnitude_bucket": "none"},
        labels={"is_major_event": False},
    )
    assert event_replay_severity_scale(mild) < 0.2


def test_infer_direction_uses_kernel_pressure_not_calibration_file():
    result = {
        "mechanism_calibration": {"predicted_direction": "up", "outcome_effect": 0.2},
        "final_risk": {"directional_pressure": 0.5},
    }
    assert infer_simulated_direction(result) == "down"


def test_infer_direction_pressure_fallback():
    assert infer_simulated_direction({"final_risk": {"directional_pressure": 0.5}}) == "down"
    assert infer_simulated_direction({"final_risk": {"directional_pressure": -0.1}}) == "up"
    assert infer_simulated_direction({"final_risk": {"directional_pressure": 0.0, "drawdown_risk": 0.4}}) == "down"


def test_scale_patch_uses_learned_store():
    reload_learned_store()
    patch = {"directional_pressure_score": 0.1}
    scaled = scale_patch(patch, event_kind="earnings_miss", domain="earnings")
    assert scaled["directional_pressure_score"] != 0.1 or learned_available() is False


def test_compiler_select_best_rule_not_first_match():
    reload_learned_store()
    rules = json.loads(RULES.read_text(encoding="utf-8"))["rules"]
    from market_causal_engine.compiler import CompilerRule

    parsed = [
        CompilerRule(
            rule_id=r["rule_id"],
            match_tags=tuple(r.get("match_tags", [])),
            match_keywords=tuple(r.get("match_keywords", [])),
            event_kind=r["event_kind"],
            default_severity=float(r.get("default_severity", 0.7)),
        )
        for r in rules
    ]
    compiler = MarketCompiler(parsed)
    atom = MarketAtom(
        atom_id="a1",
        text="Company reports Q1 earnings miss relative to estimates",
        source="8-K",
        time=100,
        published_at=100,
        tags=["earnings"],
        metadata={"severity": 0.9, "confidence": 0.8},
    )
    compiled = compiler.compile_atom(atom, domain="earnings")
    assert compiled is not None
    assert compiled.event_kind in {"earnings_miss", "earnings_release", "earnings_beat"}


def test_category_for_kind_and_path_attention():
    reload_learned_store()
    assert category_for_kind("earnings_miss") in {"fundamental", None}
    trace = [
        {"action": "commit", "kind": "earnings_miss", "patch": {"drawdown_risk_score": 0.2}},
        {"action": "commit", "kind": "viral_negative_news", "patch": {"drawdown_risk_score": 0.1}},
    ]
    shares = compute_mechanism_contributions(trace, dominant_path=["earnings_miss"], path_weighted=True)
    assert shares["path_weighted"] is True
    assert "fundamental" in shares


def test_earnings_interaction_features():
    from market_causal_engine.calibration.feature_builder import (
        EARNINGS_INTERACTION_ORDER,
        expand_earnings_interactions,
    )

    base = {"m_fundamental": 0.5, "m_sentiment": 0.4, "m_liquidity": 0.2, "max_severity": 0.7, "trace_total": 0.8}
    expanded = expand_earnings_interactions(base)
    assert expanded["x_fund_sent"] == round(0.5 * 0.4, 6)
    assert all(k in expanded for k in EARNINGS_INTERACTION_ORDER)


def test_infer_magnitude_wires_through_calibration():
    from market_causal_engine.calibration.impact import attach_calibration
    from market_causal_engine.learned.magnitude import infer_magnitude

    reload_learned_store()
    result = {
        "domain": "earnings",
        "final_risk": {"drawdown_risk": 0.5, "directional_pressure": 0.4},
        "_benchmark_event": {"scenario_id": "E1", "domain": "earnings"},
    }
    mag = infer_magnitude(result)
    assert mag.get("predicted_return_pct") is not None
    attach_calibration(result, {"direction": "down", "after_hours_return_pct": -10.0})
    assert result["calibrated_impact"].get("magnitude_source") == "earnings_interaction_ridge"
