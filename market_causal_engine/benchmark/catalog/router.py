"""Learned catalog vs scenario router (Phase 4)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from market_causal_engine.calibration.feature_builder import vectorize
from market_causal_engine.calibration.mechanism_model import TrainingSample
from market_causal_engine.counterfactuals.returns import ols_fit, rmse
from market_causal_engine.learned.features import build_inference_features

ROUTER_FEATURES = [
    "cat_pressure",
    "cat_drawdown",
    "cat_trace_total",
    "cat_pred_effect",
    "scn_pressure",
    "scn_drawdown",
    "scn_trace_total",
    "scn_pred_effect",
    "delta_pressure",
    "delta_pred_effect",
]

LEARNED_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "learned" / "catalog_router.json"


def attach_predicted_effect(
    result: dict[str, Any],
    event: dict[str, Any],
    model: Any,
) -> None:
    from market_causal_engine.learned.features import build_inference_features

    domain = str(result.get("domain") or "earnings")
    feats = build_inference_features(result, event, domain=domain, with_earnings_interactions=True)
    try:
        pred = model.predict(feats)
        result["_predicted_effect"] = float(pred["predicted_effect"])
    except Exception:  # noqa: BLE001
        result["_predicted_effect"] = 0.0


def build_router_features(
    catalog_result: dict[str, Any],
    scenario_result: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
) -> dict[str, float]:
    cat_risk = catalog_result.get("final_risk", {})
    scn_risk = scenario_result.get("final_risk", {})
    domain = str(catalog_result.get("domain") or "earnings")

    cat_feats = build_inference_features(catalog_result, event, domain=domain)
    scn_feats = build_inference_features(scenario_result, event, domain=domain)

    cat_pred = float(catalog_result.get("_predicted_effect", 0.0))
    scn_pred = float(scenario_result.get("_predicted_effect", 0.0))
    cat_p = float(cat_risk.get("directional_pressure", 0.0))
    scn_p = float(scn_risk.get("directional_pressure", 0.0))

    return {
        "cat_pressure": cat_p,
        "cat_drawdown": float(cat_risk.get("drawdown_risk", 0.0)),
        "cat_trace_total": float(cat_feats.get("trace_total", 0.0)),
        "cat_pred_effect": cat_pred,
        "scn_pressure": scn_p,
        "scn_drawdown": float(scn_risk.get("drawdown_risk", 0.0)),
        "scn_trace_total": float(scn_feats.get("trace_total", 0.0)),
        "scn_pred_effect": scn_pred,
        "delta_pressure": round(cat_p - scn_p, 6),
        "delta_pred_effect": round(cat_pred - scn_pred, 6),
    }


@dataclass
class CatalogRouterModel:
    feature_names: list[str] = field(default_factory=lambda: list(ROUTER_FEATURES))
    coefficients: list[float] = field(default_factory=list)
    threshold: float = 0.5
    training_accuracy: float | None = None
    n_samples: int = 0
    version: str = "v1.0-catalog-router"

    def fit(self, samples: list[TrainingSample], *, ridge: float = 1.0) -> CatalogRouterModel:
        if len(samples) < 20:
            raise ValueError(f"Need >= 20 router samples, got {len(samples)}")

        vectors = [vectorize(s.features, feature_order=self.feature_names) for s in samples]
        x_cols = [[vec[j] for vec in vectors] for j in range(len(self.feature_names))]
        y = [s.effect for s in samples]
        coefs = ols_fit(x_cols, y, ridge=ridge)
        if coefs is None:
            raise ValueError("Router fit failed")

        self.coefficients = [round(c, 6) for c in coefs]
        self.n_samples = len(samples)
        preds = [self.predict_score(s.features) for s in samples]
        labels = [1.0 if p >= self.threshold else 0.0 for p in preds]
        correct = sum(1 for pred, s in zip(labels, samples, strict=True) if pred == s.effect)
        self.training_accuracy = round(correct / len(samples), 4)
        preds_y = [s.effect for s in samples]
        self._training_rmse = round(rmse(preds, preds_y), 6)
        return self

    def predict_score(self, features: dict[str, float]) -> float:
        vec = vectorize(features, feature_order=self.feature_names)
        raw = self.coefficients[0] + sum(
            self.coefficients[i + 1] * vec[i + 1] for i in range(len(self.feature_names) - 1)
        )
        return 1.0 / (1.0 + pow(2.718281828, -raw))

    def prefer_catalog(self, features: dict[str, float]) -> bool:
        if not self.coefficients:
            return True
        return self.predict_score(features) >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_names": self.feature_names,
            "coefficients": self.coefficients,
            "threshold": self.threshold,
            "training_accuracy": self.training_accuracy,
            "n_samples": self.n_samples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogRouterModel:
        return cls(
            feature_names=list(data.get("feature_names", ROUTER_FEATURES)),
            coefficients=list(data.get("coefficients", [])),
            threshold=float(data.get("threshold", 0.5)),
            training_accuracy=data.get("training_accuracy"),
            n_samples=int(data.get("n_samples", 0)),
            version=str(data.get("version", "v1.0-catalog-router")),
        )


def load_catalog_router(path: str | Path | None = None) -> CatalogRouterModel | None:
    p = Path(path) if path else LEARNED_PATH
    if not p.exists():
        return None
    return CatalogRouterModel.from_dict(json.loads(p.read_text(encoding="utf-8")))


def save_catalog_router(model: CatalogRouterModel, path: str | Path | None = None) -> Path:
    out = Path(path) if path else LEARNED_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out
