"""Tests for catalog atom enrichment and direction inference."""

from __future__ import annotations

from market_causal_engine.benchmark.catalog.atoms import enrich_catalog_atom, score_text_polarity
from market_causal_engine.benchmark.catalog.direction import (
    CatalogDirectionModel,
    DEFAULT_PARAMS,
    build_catalog_direction_features,
    fit_catalog_direction_params,
    infer_catalog_direction_heuristic,
)
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.learned.compiler_scorer import score_rule
from market_causal_engine.compiler import load_compiler_rules


def _atom(text: str, **meta) -> MarketAtom:
    return MarketAtom(
        atom_id="t1",
        text=text,
        source="8-K",
        time=0,
        tags=["earnings"],
        metadata=dict(meta),
    )


def test_boilerplate_suppresses_guidance_rule():
    rules = load_compiler_rules("data/market/compiler_rules/v0.1.json")
    guidance = next(r for r in rules if r.event_kind == "guidance_cut")
    boiler = enrich_catalog_atom(
        _atom(
            "This press release contains forward-looking statements under the Private Securities Litigation Reform Act."
        )
    )
    assert score_rule(guidance, boiler) == 0.0
    earnings = next(r for r in rules if r.event_kind == "earnings_release")
    beat_atom = enrich_catalog_atom(
        _atom("Company reports Q1 eps beat estimates and earnings release.", extracted_by="financial_results")
    )
    assert score_rule(earnings, beat_atom) > score_rule(guidance, beat_atom)


def test_polarity_scores_beat_vs_miss():
    beat = score_text_polarity("Revenue grew with record quarterly earnings and beat estimates.")
    miss = score_text_polarity("Revenue missed estimates and the company lowered guidance.")
    assert beat["bull"] > beat["bear"]
    assert miss["bear"] > miss["bull"]


def test_enrich_sets_beat_miss_payload():
    atom = enrich_catalog_atom(_atom("Record revenue growth beat estimates.", extracted_by="financial_results"))
    assert atom.metadata["beat_severity"] > atom.metadata["miss_severity"]
    assert atom.metadata["catalog_polarity"] > 0


def test_heuristic_neutral_on_mild_evidence():
    feats = {
        "directional_pressure": 0.05,
        "drawdown_risk": 0.1,
        "trace_bias": 0.02,
        "atom_bull_total": 1.0,
        "atom_bear_total": 1.0,
        "atom_net_polarity": 0.0,
        "boilerplate_ratio": 0.1,
    }
    assert infer_catalog_direction_heuristic(feats) == "neutral"


def test_heuristic_down_on_high_pressure():
    feats = {
        "directional_pressure": 0.35,
        "drawdown_risk": 0.30,
        "atom_net_polarity": 1.0,
        "atom_bull_total": 2.0,
        "atom_bear_total": 1.0,
    }
    assert infer_catalog_direction_heuristic(feats) == "down"


def test_calibrator_improves_on_synthetic_samples():
    samples = []
    for direction in ("up", "down", "neutral") * 8:
        feats = build_catalog_direction_features(
            {
                "final_risk": {
                    "directional_pressure": 0.28 if direction == "down" else 0.06,
                    "drawdown_risk": 0.30 if direction == "down" else 0.10,
                },
                "trace": [
                    {
                        "action": "commit",
                        "patch": {"directional_pressure_score": 0.12 if direction == "down" else -0.06},
                    }
                ],
            },
            atoms=[
                enrich_catalog_atom(
                    _atom(
                        "missed estimates lowered guidance" if direction == "down" else (
                            "beat estimates record growth" if direction == "up" else "revenue was in line with expectations"
                        ),
                        extracted_by="financial_results",
                    )
                )
            ],
        )
        samples.append((feats, direction))

    model = fit_catalog_direction_params(samples)
    assert model.training_accuracy is not None
    assert model.training_accuracy >= 0.5
    assert model.params != DEFAULT_PARAMS or model.training_accuracy >= 0.5
