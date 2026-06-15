"""Catalog-feed direction inference and training."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.catalog.atoms import catalog_atom_summary
from market_causal_engine.calibration.feature_builder import build_case_features
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.learned.direction import _trace_pressure_bias

CATALOG_DIRECTION_FEATURES = [
    "directional_pressure",
    "drawdown_risk",
    "trace_bias",
    "atom_bull_total",
    "atom_bear_total",
    "atom_net_polarity",
    "atom_max_severity",
    "atom_count",
    "boilerplate_ratio",
    "m_fundamental",
    "m_sentiment",
    "trace_total",
]

DEFAULT_PARAMS: dict[str, float] = {
    "neutral_pressure_max": 0.14,
    "neutral_drawdown_max": 0.22,
    "hard_down_pressure": 0.20,
    "hard_down_drawdown": 0.26,
    "strong_beat_net": 4.0,
    "strong_beat_bull": 5.0,
    "medium_down_net": -1.5,
    "medium_up_net": 3.0,
    "medium_up_pressure_max": 0.18,
}

LEARNED_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "learned" / "catalog_direction.json"


def build_catalog_direction_features(
    result: dict[str, Any],
    *,
    atoms: list[MarketAtom] | None = None,
) -> dict[str, float]:
    risk = result.get("final_risk", {})
    summary = catalog_atom_summary(atoms or [])
    trace_feats = build_case_features(claims=[], trace=result.get("trace"), domain="earnings")

    return {
        "directional_pressure": round(float(risk.get("directional_pressure", 0.0)), 6),
        "drawdown_risk": round(float(risk.get("drawdown_risk", 0.0)), 6),
        "trace_bias": _trace_pressure_bias(result.get("trace", [])),
        "atom_bull_total": float(summary["bull_total"]),
        "atom_bear_total": float(summary["bear_total"]),
        "atom_net_polarity": float(summary["net_polarity"]),
        "atom_max_severity": float(summary["max_severity"]),
        "atom_count": float(summary["atom_count"]),
        "boilerplate_ratio": float(summary["boilerplate_ratio"]),
        "m_fundamental": float(trace_feats.get("m_fundamental", 0.0)),
        "m_sentiment": float(trace_feats.get("m_sentiment", 0.0)),
        "trace_total": float(trace_feats.get("trace_total", 0.0)),
    }


def infer_catalog_direction_heuristic(
    features: dict[str, float],
    params: dict[str, float] | None = None,
) -> str:
    """
    Catalog direction tiers:
    1) High kernel stress → down (earnings miss / guidance path), unless extreme beat language.
    2) Mild kernel → neutral (filing tone without market stress).
    3) Medium band → atom polarity tie-break.
    """
    p = {**DEFAULT_PARAMS, **(params or {})}

    pressure = float(features.get("directional_pressure", 0.0))
    drawdown = float(features.get("drawdown_risk", 0.0))
    net = float(features.get("atom_net_polarity", 0.0))
    bull = float(features.get("atom_bull_total", 0.0))
    bear = float(features.get("atom_bear_total", 0.0))

    if pressure >= p["hard_down_pressure"] or drawdown >= p["hard_down_drawdown"]:
        if net >= p["strong_beat_net"] and bull >= p["strong_beat_bull"] and bear <= 2:
            return "up"
        return "down"

    if pressure < p["neutral_pressure_max"] and drawdown < p["neutral_drawdown_max"]:
        return "neutral"

    if net <= p["medium_down_net"] or bear >= bull + 2:
        return "down"
    if net >= p["medium_up_net"] and pressure <= p["medium_up_pressure_max"] and bull >= bear + 1:
        return "up"
    return "neutral"


@dataclass
class CatalogDirectionModel:
    params: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    training_accuracy: float | None = None
    n_samples: int = 0
    version: str = "v1.2-catalog-tiered"

    def predict_direction(self, features: dict[str, float]) -> str:
        return infer_catalog_direction_heuristic(features, self.params)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "params": self.params,
            "training_accuracy": self.training_accuracy,
            "n_samples": self.n_samples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogDirectionModel:
        return cls(
            params={**DEFAULT_PARAMS, **data.get("params", {})},
            training_accuracy=data.get("training_accuracy"),
            n_samples=int(data.get("n_samples", 0)),
            version=str(data.get("version", "v1.2-catalog-tiered")),
        )


def load_catalog_direction_model(path: str | Path | None = None) -> CatalogDirectionModel | None:
    p = Path(path) if path else LEARNED_PATH
    if not p.exists():
        return None
    return CatalogDirectionModel.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_catalog_direction_model(model: CatalogDirectionModel, path: str | Path | None = None) -> Path:
    out = Path(path) if path else LEARNED_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def infer_catalog_direction(
    result: dict[str, Any],
    *,
    atoms: list[MarketAtom] | None = None,
    model: CatalogDirectionModel | None = None,
) -> str:
    features = build_catalog_direction_features(result, atoms=atoms)
    loaded = model or load_catalog_direction_model()
    if loaded:
        return loaded.predict_direction(features)
    return infer_catalog_direction_heuristic(features)


def _direction_match(observed: str, predicted: str) -> bool:
    if observed == "neutral":
        return predicted == "neutral"
    return observed == predicted


def fit_catalog_direction_params(
    samples: list[tuple[dict[str, float], str]],
) -> CatalogDirectionModel:
    if len(samples) < 12:
        raise ValueError(f"Need >= 12 samples, got {len(samples)}")

    grid = {
        "neutral_pressure_max": (0.10, 0.14, 0.18),
        "hard_down_pressure": (0.16, 0.20, 0.24, 0.28),
        "hard_down_drawdown": (0.22, 0.26, 0.30),
        "strong_beat_net": (3.0, 4.0, 5.0),
        "medium_down_net": (-1.0, -1.5, -2.0),
        "medium_up_net": (2.0, 3.0, 4.0),
    }

    keys = list(grid.keys())
    combos = list(product(*(grid[k] for k in keys)))
    if len(samples) > 200 and len(combos) > 400:
        import random

        random.seed(42)
        combos = random.sample(combos, 400)

    best_params = dict(DEFAULT_PARAMS)
    best_acc = 0.0
    for combo in combos:
        trial = dict(DEFAULT_PARAMS)
        for key, val in zip(keys, combo, strict=True):
            trial[key] = val
        correct = sum(
            1 for feats, obs in samples if _direction_match(obs, infer_catalog_direction_heuristic(feats, trial))
        )
        acc = correct / len(samples)
        if acc > best_acc:
            best_acc = acc
            best_params = trial

    return CatalogDirectionModel(
        params=best_params,
        training_accuracy=round(best_acc, 4),
        n_samples=len(samples),
    )


def training_sample_from_event(
    result: dict[str, Any],
    *,
    observed_direction: str,
    atoms: list[MarketAtom],
) -> tuple[dict[str, float], str]:
    feats = build_catalog_direction_features(result, atoms=atoms)
    return feats, str(observed_direction)
