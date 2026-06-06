"""Tests for Market Event Causal Engine — three MVP product lines."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_causal_engine.analysis import enrich_result
from market_causal_engine.compiler import MarketCompiler, load_compiler_rules
from market_causal_engine.constants import DOMAIN_REGISTRY, SCENARIO_FILES, WORLD_IDS
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.registry import register_all_mechanisms, MECHANISM_INDEX
from market_causal_engine.reverse import analyze_result, diff_results, infer_market_regime
from market_causal_engine.scenarios import run_counterfactual_suite, run_scenario


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "data" / "market" / "scenarios"


@pytest.fixture(scope="module", autouse=True)
def _register_mechanisms():
    register_all_mechanisms()


def test_mechanisms_registered():
    assert "earnings_release" in MECHANISM_INDEX
    assert "fomc_statement" in MECHANISM_INDEX
    assert "short_seller_report" in MECHANISM_INDEX
    assert "beta_transmission" in MECHANISM_INDEX
    assert len(MECHANISM_INDEX) >= 35


def test_domain_registry_cover_all_directions():
    assert set(DOMAIN_REGISTRY.keys()) == {"earnings", "short_report", "macro"}
    all_ids = []
    for group in DOMAIN_REGISTRY.values():
        all_ids.extend(group["scenarios"])
    for sid in all_ids:
        assert sid in SCENARIO_FILES


# --- MVP 1: Earnings ---


def test_e1_earnings_guidance_baseline():
    path = SCENARIOS / SCENARIO_FILES["E1"]
    result = run_scenario(path, world_id="W0", until=15)

    assert result["domain"] == "earnings"
    assert result["scenario_id"] == "E1_earnings_guidance_cut"
    risk = result["final_risk"]
    assert 0.15 < risk["drawdown_risk"] < 0.95
    assert risk["directional_pressure"] > 0.15


def test_e1_counterfactual_no_downgrade():
    path = SCENARIOS / SCENARIO_FILES["E1"]
    w0 = run_scenario(path, world_id="W0", until=15)
    w1 = run_scenario(path, world_id="W1", until=15)
    assert w1["final_risk"]["drawdown_risk"] < w0["final_risk"]["drawdown_risk"]


def test_e1_mechanism_contributions():
    path = SCENARIOS / SCENARIO_FILES["E1"]
    result = run_scenario(path, world_id="W0", until=15)
    contrib = result["mechanism_contributions"]
    assert contrib["fundamental"] + contrib["sentiment"] + contrib["liquidity"] > 0


def test_e2_earnings_beat_rally():
    path = SCENARIOS / SCENARIO_FILES["E2"]
    result = run_scenario(path, world_id="W0", until=12)
    assert result["mvp_output"]["move_direction"] in ("up", "neutral")
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "earnings_beat" in kinds


def test_e1_feed_driven():
    path = SCENARIOS / SCENARIO_FILES["E1"]
    feed = ROOT / "data" / "market" / "atoms" / "E1_feed.jsonl"
    result = run_scenario(path, world_id="W0", until=10, feed_path=feed)
    assert len(result.get("compiled_events", [])) >= 3


# --- MVP 2: Short report ---


def test_s1_short_report_trust_path():
    path = SCENARIOS / SCENARIO_FILES["S1"]
    result = run_scenario(path, world_id="W0", until=12)
    assert result["mvp"] == "short_report"
    mvp = result["mvp_output"]
    assert "trust_impact_path" in mvp
    assert mvp["liquidity_pressure"] > 0
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "short_seller_report" in kinds
    assert "trust_erosion" in kinds


def test_s2_regulatory_continuation():
    path = SCENARIOS / SCENARIO_FILES["S2"]
    result = run_scenario(path, world_id="W0", until=12)
    mvp = result["mvp_output"]
    assert mvp["regulatory_risk"] > 0.2
    assert mvp["continuation_vs_reversal"]["likely_mechanism"] == "continued_pressure"


def test_s1_w2_suppresses_social():
    path = SCENARIOS / SCENARIO_FILES["S1"]
    w0 = run_scenario(path, world_id="W0", until=12)
    w2 = run_scenario(path, world_id="W2", until=12)
    assert w2["final_risk"]["volatility_risk"] <= w0["final_risk"]["volatility_risk"]


def test_s1_feed_driven():
    path = SCENARIOS / SCENARIO_FILES["S1"]
    feed = ROOT / "data" / "market" / "atoms" / "S1_feed.jsonl"
    result = run_scenario(path, world_id="W0", until=8, feed_path=feed)
    assert result.get("compiled_events")


# --- MVP 3: Macro ---


def test_x1_fomc_transmission():
    path = SCENARIOS / SCENARIO_FILES["X1"]
    result = run_scenario(path, world_id="W0", until=12)
    assert result["mvp"] == "macro"
    mvp = result["mvp_output"]
    assert "macro_transmission_path" in mvp
    assert len(mvp["macro_to_sector_to_stock"]) >= 1
    kinds = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "fomc_statement" in kinds
    assert "beta_transmission" in kinds


def test_x2_cpi_rotation_beta():
    path = SCENARIOS / SCENARIO_FILES["X2"]
    result = run_scenario(path, world_id="W0", until=12)
    state = result["final_state"]
    assert state.get("bond_yield_pressure", 0) > 0.1
    assert state.get("growth_value_tilt", 0) > 0.1


def test_x1_w5_macro_suppressed():
    path = SCENARIOS / SCENARIO_FILES["X1"]
    w0 = run_scenario(path, world_id="W0", until=10)
    w5 = run_scenario(path, world_id="W5", until=10)
    assert w5["final_risk"]["directional_pressure"] < w0["final_risk"]["directional_pressure"]


def test_x1_feed_driven():
    path = SCENARIOS / SCENARIO_FILES["X1"]
    feed = ROOT / "data" / "market" / "atoms" / "X1_feed.jsonl"
    result = run_scenario(path, world_id="W0", until=8, feed_path=feed)
    assert result.get("compiled_events")


# --- Shared ---


def test_legacy_m1_alias():
    path = SCENARIOS / SCENARIO_FILES["M1"]
    result = run_scenario(path, world_id="W0", until=15)
    assert result["mvp"] == "earnings"


def test_compiler_rules_all_mvps():
    rules_path = ROOT / "data" / "market" / "compiler_rules" / "v0.1.json"
    compiler = MarketCompiler(load_compiler_rules(rules_path))
    samples = [
        MarketAtom("1", "Company lowers FY2026 revenue guidance", "filing", 2, ["earnings", "guidance"]),
        MarketAtom("2", "Short seller publishes fraud report", "research", 0, ["short", "research"]),
        MarketAtom("3", "FOMC statement more hawkish than expected", "macro", 0, ["fomc", "macro"]),
    ]
    kinds = {compiler.compile_atom(a).event_kind for a in samples if compiler.compile_atom(a)}
    assert "guidance_cut" in kinds
    assert "short_seller_report" in kinds
    assert "fomc_statement" in kinds


def test_counterfactual_suite_e1():
    path = SCENARIOS / SCENARIO_FILES["E1"]
    suite = run_counterfactual_suite(path, worlds=["W0", "W1", "W3"], until=15)
    assert "W1" in suite["counterfactual_diffs"]


def test_all_world_intervention_files_exist():
    for wid in WORLD_IDS:
        if wid == "W0":
            continue
        assert (ROOT / "data" / "market" / "interventions" / f"{wid}.json").exists()
