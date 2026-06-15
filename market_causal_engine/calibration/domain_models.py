"""Per-domain mechanism models (earnings / macro / short_report)."""

from __future__ import annotations

import json
from pathlib import Path

from market_causal_engine.calibration.feature_builder import (
    EARNINGS_FEATURE_ORDER,
    FEATURE_ORDER,
    expand_earnings_interactions,
)
from market_causal_engine.calibration.mechanism_model import MechanismModel, TrainingSample

DOMAINS = ("earnings", "macro", "short_report")


def _expand_sample(sample: TrainingSample) -> TrainingSample:
    return TrainingSample(
        event_id=sample.event_id,
        features=expand_earnings_interactions(dict(sample.features)),
        effect=sample.effect,
        domain=sample.domain,
        source=sample.source,
    )


def train_domain_models(
    samples: list[TrainingSample],
    *,
    min_samples: int = 8,
) -> dict[str, MechanismModel]:
    by_domain: dict[str, list[TrainingSample]] = {d: [] for d in DOMAINS}
    for sample in samples:
        domain = sample.domain if sample.domain in DOMAINS else "earnings"
        by_domain[domain].append(sample)

    models: dict[str, MechanismModel] = {}
    pooled = [s for group in by_domain.values() for s in group]
    fallback = MechanismModel().fit(pooled) if len(pooled) >= min_samples else None

    for domain, rows in by_domain.items():
        if len(rows) >= min_samples:
            if domain == "earnings":
                expanded = [_expand_sample(s) for s in rows]
                models[domain] = MechanismModel(feature_names=list(EARNINGS_FEATURE_ORDER)).fit(expanded)
            else:
                models[domain] = MechanismModel(feature_names=list(FEATURE_ORDER)).fit(rows)
        elif fallback is not None:
            models[domain] = fallback
    return models


def save_domain_models(models: dict[str, MechanismModel], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v0.9-earnings-interaction",
        "models": {domain: model.to_dict() for domain, model in models.items()},
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def save_earnings_magnitude_model(model: MechanismModel, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v0.9-earnings-interaction",
        "model": model.to_dict(),
        "feature_order": list(EARNINGS_FEATURE_ORDER),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def load_domain_models(path: str | Path) -> dict[str, MechanismModel]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {domain: MechanismModel.from_dict(payload) for domain, payload in data.get("models", {}).items()}


def load_earnings_magnitude_model(path: str | Path) -> MechanismModel | None:
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    payload = data.get("model")
    if not payload:
        return None
    return MechanismModel.from_dict(payload)
