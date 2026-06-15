"""Learned 3-way direction classifier for catalog feed replay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from market_causal_engine.calibration.feature_builder import EARNINGS_FEATURE_ORDER, vectorize
from market_causal_engine.calibration.mechanism_model import MechanismModel
from market_causal_engine.counterfactuals.returns import ols_fit
from market_causal_engine.extraction.patterns import infer_tone
from market_causal_engine.learned.features import build_inference_features

DIRECTION_CLASSES = ("down", "neutral", "up")

CATALOG_DIRECTION_EXTRA = (
    "kernel_pressure",
    "kernel_drawdown",
    "trace_pressure_bias",
    "pred_effect",
    "claim_count",
    "claim_tone_net",
    "claim_polarity_net",
    "fundamental_claim_mass",
    "sentiment_claim_mass",
    "avg_claim_confidence",
    "max_abs_claim_polarity",
    "llm_event_proposer",
    "catalog_quality_score",
    "x_tone_pressure",
    "x_tone_effect",
    "x_polarity_pressure",
)

CATALOG_DIRECTION_FEATURE_ORDER = [*EARNINGS_FEATURE_ORDER, *CATALOG_DIRECTION_EXTRA]

LEARNED_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "learned" / "catalog_direction_model.json"
)


def _trace_pressure_bias(trace: list[dict[str, Any]]) -> float:
    bull = 0.0
    bear = 0.0
    for entry in trace:
        if entry.get("action") != "commit":
            continue
        delta = float(entry.get("patch", {}).get("directional_pressure_score", 0.0) or 0.0)
        if delta < 0:
            bull += abs(delta)
        elif delta > 0:
            bear += delta
    return round(bull - bear, 6)


def _claim_aggregate_features(result: dict[str, Any]) -> dict[str, float]:
    claims = []
    raw = result.get("causal_claims")
    llm_event = 0.0
    quality = 0.0
    if isinstance(raw, dict):
        claims = list(raw.get("accepted") or [])
        llm_event = 1.0 if str(raw.get("llm_proposer", "")) == "llm_event" else 0.0
        quality = float(raw.get("catalog_quality_score", 0.0))

    if not claims:
        return {
            "claim_count": 0.0,
            "claim_tone_net": 0.0,
            "claim_polarity_net": 0.0,
            "fundamental_claim_mass": 0.0,
            "sentiment_claim_mass": 0.0,
            "avg_claim_confidence": 0.0,
            "max_abs_claim_polarity": 0.0,
            "llm_event_proposer": llm_event,
            "catalog_quality_score": quality,
        }

    polarity_weighted = 0.0
    tone_weighted = 0.0
    weight_total = 0.0
    fund_mass = 0.0
    sent_mass = 0.0
    confs: list[float] = []
    abs_pols: list[float] = []
    for claim in claims:
        text = " ".join(
            str(claim.get(key, "")) for key in ("cause", "effect", "evidence_span") if claim.get(key)
        )
        weight = float(claim.get("severity", 0.0)) * float(claim.get("confidence", 1.0))
        if weight <= 0:
            weight = float(claim.get("confidence", 0.5))
        polarity = float(claim.get("polarity", infer_tone(text)))
        tone = infer_tone(text)
        polarity_weighted += polarity * weight
        tone_weighted += tone * weight
        weight_total += abs(weight)
        confs.append(float(claim.get("confidence", 0.0)))
        abs_pols.append(abs(polarity))
        mech = str(claim.get("mechanism", "")).lower()
        if mech == "fundamental":
            fund_mass += weight
        elif mech == "sentiment":
            sent_mass += weight

    return {
        "claim_count": float(len(claims)),
        "claim_tone_net": round(tone_weighted / (weight_total or 1.0), 6),
        "claim_polarity_net": round(polarity_weighted / (weight_total or 1.0), 6),
        "fundamental_claim_mass": round(fund_mass, 6),
        "sentiment_claim_mass": round(sent_mass, 6),
        "avg_claim_confidence": round(sum(confs) / len(confs), 6) if confs else 0.0,
        "max_abs_claim_polarity": round(max(abs_pols), 6) if abs_pols else 0.0,
        "llm_event_proposer": llm_event,
        "catalog_quality_score": quality,
    }


def build_catalog_direction_features(
    result: dict[str, Any],
    event: dict[str, Any] | None,
    *,
    domain_model: MechanismModel | None = None,
) -> dict[str, float]:
    domain = str(result.get("domain") or "earnings")
    feats = build_inference_features(result, event, domain=domain, with_earnings_interactions=True)
    risk = result.get("final_risk", {})
    pred_effect = 0.0
    if domain_model is not None:
        try:
            pred_effect = float(domain_model.predict(feats)["predicted_effect"])
        except Exception:  # noqa: BLE001
            pred_effect = float(result.get("_predicted_effect", 0.0))
    else:
        pred_effect = float(result.get("_predicted_effect", 0.0))

    feats["kernel_pressure"] = float(risk.get("directional_pressure", 0.0))
    feats["kernel_drawdown"] = float(risk.get("drawdown_risk", 0.0))
    feats["trace_pressure_bias"] = _trace_pressure_bias(result.get("trace", []))
    feats["pred_effect"] = round(pred_effect, 6)
    feats.update(_claim_aggregate_features(result))
    tone = float(feats.get("claim_tone_net", 0.0))
    polarity = float(feats.get("claim_polarity_net", 0.0))
    pressure = float(feats.get("kernel_pressure", 0.0))
    feats["x_tone_pressure"] = round(tone * pressure, 6)
    feats["x_tone_effect"] = round(tone * pred_effect, 6)
    feats["x_polarity_pressure"] = round(polarity * pressure, 6)
    return feats


@dataclass
class DirectionSample:
    event_id: str
    event_date: str
    features: dict[str, float]
    direction: str


@dataclass
class CatalogDirectionModel:
    feature_names: list[str] = field(default_factory=lambda: list(CATALOG_DIRECTION_FEATURE_ORDER))
    classifiers: dict[str, list[float]] = field(default_factory=dict)
    training_accuracy: float | None = None
    holdout_accuracy: float | None = None
    confidence_margin: float = 0.10
    n_samples: int = 0
    n_holdout: int = 0
    version: str = "v1.0-catalog-direction"

    def fit(
        self,
        samples: list[DirectionSample],
        *,
        ridge: float = 1.0,
        holdout_ratio: float = 0.2,
        balance_classes: bool = False,
    ) -> CatalogDirectionModel:
        if len(samples) < 40:
            raise ValueError(f"Need >= 40 direction samples, got {len(samples)}")

        ordered = sorted(samples, key=lambda s: s.event_date)
        split = max(1, int(len(ordered) * (1.0 - holdout_ratio)))
        holdout = ordered[split:]
        train = _balance_direction_samples(ordered[:split]) if balance_classes else ordered[:split]

        self.classifiers = {}
        for label in DIRECTION_CLASSES:
            vectors = [vectorize(s.features, feature_order=self.feature_names) for s in train]
            x_cols = [[vec[j] for vec in vectors] for j in range(len(self.feature_names))]
            y = [1.0 if s.direction == label else 0.0 for s in train]
            coefs = ols_fit(x_cols, y, ridge=ridge)
            if coefs is None:
                raise ValueError(f"Direction fit failed for class {label}")
            self.classifiers[label] = [round(c, 6) for c in coefs]

        self.n_samples = len(train)
        self.n_holdout = len(holdout)
        self.training_accuracy = round(self._accuracy(train), 4)
        self.holdout_accuracy = round(self._accuracy(holdout), 4) if holdout else None
        self.confidence_margin = self._fit_confidence_margin(holdout)
        if holdout:
            self.holdout_accuracy = round(
                self._accuracy(holdout, margin=self.confidence_margin), 4
            )
        return self

    def _fit_confidence_margin(self, holdout: list[DirectionSample]) -> float:
        if len(holdout) < 20:
            return 0.10
        best_margin = 0.10
        best_acc = 0.0
        for i in range(0, 21):
            margin = i / 100.0
            acc = self._accuracy(holdout, margin=margin)
            if acc >= best_acc:
                best_acc = acc
                best_margin = margin
        return round(best_margin, 4)

    def _pressure_direction(self, features: dict[str, float]) -> str:
        pressure = float(features.get("kernel_pressure", 0.0))
        drawdown = float(features.get("kernel_drawdown", 0.0))
        if pressure >= 0.12 or drawdown >= 0.35:
            return "down"
        if pressure <= -0.05:
            return "up"
        return "neutral"

    def _class_scores(self, features: dict[str, float]) -> dict[str, float]:
        vec = vectorize(features, feature_order=self.feature_names)
        scores: dict[str, float] = {}
        for label, coefs in self.classifiers.items():
            raw = coefs[0] + sum(
                coefs[i + 1] * vec[i + 1] for i in range(len(self.feature_names) - 1)
            )
            scores[label] = 1.0 / (1.0 + pow(2.718281828, -raw))
        return scores

    def _low_confidence_direction(self, features: dict[str, float]) -> str:
        effect = float(features.get("pred_effect", 0.0))
        if effect >= 0.012:
            return "up"
        if effect <= -0.012:
            return "down"
        claim_count = float(features.get("claim_count", 0.0))
        polarity = float(features.get("claim_polarity_net", 0.0))
        if claim_count >= 2.0 and abs(polarity) >= 0.10:
            if polarity > 0:
                return "up"
            if polarity < 0:
                return "down"
        return self._pressure_direction(features)

    def predict_direction(self, features: dict[str, float], *, margin: float | None = None) -> str:
        if not self.classifiers:
            raise ValueError("Direction model not fitted")
        scores = self._class_scores(features)
        ordered = sorted(scores.values())
        spread = ordered[-1] - ordered[-2] if len(ordered) > 1 else ordered[-1]
        threshold = self.confidence_margin if margin is None else margin
        if spread < threshold:
            return self._low_confidence_direction(features)
        return max(scores, key=scores.get)

    def _accuracy(self, samples: list[DirectionSample], *, margin: float | None = None) -> float:
        if not samples:
            return 0.0
        correct = sum(
            1 for s in samples if self.predict_direction(s.features, margin=margin) == s.direction
        )
        return correct / len(samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_names": self.feature_names,
            "classifiers": self.classifiers,
            "training_accuracy": self.training_accuracy,
            "holdout_accuracy": self.holdout_accuracy,
            "confidence_margin": self.confidence_margin,
            "n_samples": self.n_samples,
            "n_holdout": self.n_holdout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogDirectionModel:
        return cls(
            feature_names=list(data.get("feature_names", CATALOG_DIRECTION_FEATURE_ORDER)),
            classifiers={k: list(v) for k, v in data.get("classifiers", {}).items()},
            training_accuracy=data.get("training_accuracy"),
            holdout_accuracy=data.get("holdout_accuracy"),
            confidence_margin=float(data.get("confidence_margin", 0.10)),
            n_samples=int(data.get("n_samples", 0)),
            n_holdout=int(data.get("n_holdout", 0)),
            version=str(data.get("version", "v1.0-catalog-direction")),
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


def _balance_direction_samples(samples: list[DirectionSample]) -> list[DirectionSample]:
    import random

    by_dir: dict[str, list[DirectionSample]] = {d: [] for d in DIRECTION_CLASSES}
    for sample in samples:
        by_dir[sample.direction].append(sample)
    max_n = max(len(items) for items in by_dir.values())
    rng = random.Random(42)
    balanced: list[DirectionSample] = []
    for direction in DIRECTION_CLASSES:
        items = by_dir[direction]
        if not items:
            continue
        for i in range(max_n):
            balanced.append(items[i % len(items)])
    rng.shuffle(balanced)
    return balanced


def collect_direction_samples(
    events: list[Any],
    *,
    domain_model: MechanismModel,
    max_events: int | None = None,
    claims_policy: Any | None = None,
) -> list[DirectionSample]:
    from market_causal_engine.benchmark.catalog.claims import has_effective_catalog_claims
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
    from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event

    samples: list[DirectionSample] = []
    for event in events:
        if event.metadata.get("synthetic_labels"):
            continue
        if not _has_usable_atoms(event.event_id):
            continue
        if claims_policy is not None:
            if not has_effective_catalog_claims(event.event_id, policy=claims_policy):
                continue
        else:
            from market_causal_engine.benchmark.catalog.claims import has_catalog_claims

            if not has_catalog_claims(event.event_id):
                continue
        direction = event.observed_outcomes.get("direction")
        if direction not in DIRECTION_CLASSES:
            continue
        try:
            result = replay_catalog_feed_event(
                event,
                until=60,
                claims_policy=claims_policy,
            )
            feats = build_catalog_direction_features(result, event.to_dict(), domain_model=domain_model)
            samples.append(
                DirectionSample(
                    event_id=event.event_id,
                    event_date=str(event.event_date),
                    features=feats,
                    direction=str(direction),
                )
            )
        except Exception:  # noqa: BLE001
            continue
        if max_events is not None and len(samples) >= max_events:
            break
    return samples
