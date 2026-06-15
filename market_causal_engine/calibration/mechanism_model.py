"""Ridge regression model: mechanism features -> Phase 1 outcome effect."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from market_causal_engine.calibration.feature_builder import FEATURE_ORDER, MECHANISM_BUCKETS, vectorize
from market_causal_engine.counterfactuals.returns import ols_fit, rmse

MODEL_VERSION = "v0.7-ridge"


@dataclass
class TrainingSample:
    event_id: str
    features: dict[str, float]
    effect: float
    domain: str = "earnings"
    source: str = "case"


@dataclass
class MechanismModel:
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_ORDER))
    coefficients: list[float] = field(default_factory=list)
    training_rmse: float | None = None
    n_samples: int = 0
    version: str = MODEL_VERSION

    def fit(self, samples: list[TrainingSample], *, ridge: float = 1.0) -> MechanismModel:
        if len(samples) < 3:
            raise ValueError("Need at least 3 training samples")

        vectors = [vectorize(s.features, feature_order=self.feature_names) for s in samples]
        x_cols = [[vec[j] for vec in vectors] for j in range(len(self.feature_names))]
        y = [s.effect for s in samples]
        coefs = ols_fit(x_cols, y, ridge=ridge)
        if coefs is None:
            raise ValueError("Mechanism model fit failed")

        self.coefficients = [round(c, 6) for c in coefs]
        self.n_samples = len(samples)
        preds = [self.predict(s.features)["predicted_effect"] for s in samples]
        self.training_rmse = round(rmse(preds, y), 6)
        return self

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        if not self.coefficients:
            raise ValueError("Model not fitted")

        vec = vectorize(features, feature_order=self.feature_names)
        pred = self.coefficients[0] + sum(self.coefficients[i + 1] * vec[i + 1] for i in range(len(self.feature_names) - 1))
        direction = "down" if pred < -0.005 else ("up" if pred > 0.005 else "neutral")
        confidence = self._confidence(features, pred)
        return {
            "predicted_effect": round(pred, 6),
            "predicted_direction": direction,
            "confidence": confidence,
            "mechanism_weights": self.mechanism_weights(features),
        }

    def mechanism_weights(self, features: dict[str, float]) -> dict[str, float]:
        raw: dict[str, float] = {}
        for bucket in MECHANISM_BUCKETS:
            feat_key = f"m_{bucket}"
            if feat_key not in self.feature_names:
                continue
            idx = self.feature_names.index(feat_key)
            feat_val = float(features.get(feat_key, 0.0))
            coef = self.coefficients[idx + 1] if idx + 1 < len(self.coefficients) else 0.0
            raw[bucket] = max(0.0, feat_val * (1.0 + abs(coef)))

        total = sum(raw.values()) or 1.0
        return {k: round(v / total, 4) for k, v in raw.items()}

    def _confidence(self, features: dict[str, float], predicted_effect: float) -> float:
        mean_conf = float(features.get("mean_confidence", 0.5))
        max_sev = float(features.get("max_severity", 0.5))
        base = 0.45 + 0.2 * mean_conf + 0.15 * max_sev
        if self.training_rmse is not None and self.training_rmse > 0:
            base *= max(0.5, 1.0 - min(0.5, self.training_rmse / 0.15))
        if abs(predicted_effect) < 0.01:
            base *= 0.85
        return round(min(0.98, base), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_names": self.feature_names,
            "coefficients": self.coefficients,
            "training_rmse": self.training_rmse,
            "n_samples": self.n_samples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MechanismModel:
        model = cls(
            feature_names=list(data.get("feature_names", FEATURE_ORDER)),
            coefficients=list(data.get("coefficients", [])),
            training_rmse=data.get("training_rmse"),
            n_samples=int(data.get("n_samples", 0)),
            version=str(data.get("version", MODEL_VERSION)),
        )
        return model


def save_model(model: MechanismModel, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def load_model(path: str | Path) -> MechanismModel:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return MechanismModel.from_dict(data)


def default_model_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "market" / "calibration" / "mechanism_model.json"
