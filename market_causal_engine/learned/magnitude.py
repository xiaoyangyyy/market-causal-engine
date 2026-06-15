"""Learned magnitude / return inference for earnings domain."""

from __future__ import annotations

from typing import Any

from market_causal_engine.learned.direction import infer_direction
from market_causal_engine.learned.features import build_inference_features
from market_causal_engine.learned.store import learned_available, load_learned_store


def infer_magnitude(
    result: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    learned: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Predict signed abnormal return (fraction) and return % from learned earnings model."""
    store = learned or (load_learned_store() if learned_available() else {})
    event = event or (result or {}).get("_benchmark_event")
    domain = str(result.get("domain") or (event or {}).get("domain") or "earnings")

    model = store.get("earnings_magnitude_model") or store.get("domain_models", {}).get(domain)
    if model is None:
        return {"predicted_effect": None, "predicted_return_pct": None, "source": "none"}

    features = build_inference_features(result, event, domain=domain, with_earnings_interactions=True)
    try:
        pred = model.predict(features)
    except Exception:  # noqa: BLE001
        return {"predicted_effect": None, "predicted_return_pct": None, "source": "error"}

    effect = float(pred.get("predicted_effect", 0.0))
    direction = infer_direction(result, event=event, learned=store)
    if direction == "down" and effect > 0:
        effect = -abs(effect)
    elif direction == "up" and effect < 0:
        effect = abs(effect)
    elif direction == "neutral":
        effect *= 0.35

    return {
        "predicted_effect": round(effect, 6),
        "predicted_return_pct": round(effect * 100.0, 2),
        "predicted_direction": direction,
        "confidence": pred.get("confidence"),
        "source": "earnings_interaction_ridge",
    }


def infer_return_pct(
    result: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    learned: dict[str, Any] | None = None,
) -> float | None:
    out = infer_magnitude(result, event=event, learned=learned)
    val = out.get("predicted_return_pct")
    return float(val) if val is not None else None
