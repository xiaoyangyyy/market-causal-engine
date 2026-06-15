"""Learned direction inference (replaces pressure thresholds)."""

from __future__ import annotations

from typing import Any

from market_causal_engine.calibration.feature_builder import (
    build_case_features,
    features_from_scenario_template,
)

CATALOG_POLARITY_NET_THRESHOLD = 0.08


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


def _scenario_polarity(event: dict[str, Any] | None, *, pressure: float, drawdown: float) -> str | None:
    if not event:
        return None
    scenario_id = str(event.get("scenario_id") or "")
    if scenario_id == "E2" and pressure <= 0.08:
        return "up"
    if scenario_id == "E1" and pressure >= 0.08 and drawdown >= 0.12:
        return "down"
    return None


def _catalog_polarity_direction(result: dict[str, Any]) -> str:
    claims = result.get("causal_claims")
    if not isinstance(claims, dict):
        return "neutral"
    net = claims.get("catalog_net_polarity")
    if net is None:
        from market_causal_engine.benchmark.catalog.claim_quality import net_polarity

        net = net_polarity(claims.get("accepted") or [])
    net = float(net)
    if net >= CATALOG_POLARITY_NET_THRESHOLD:
        return "up"
    if net <= -CATALOG_POLARITY_NET_THRESHOLD:
        return "down"
    return "neutral"


def _catalog_consensus_direction(
    result: dict[str, Any],
    *,
    event: dict[str, Any] | None,
    domain_model: Any,
) -> str:
    """Use domain model + claim polarity when they agree; otherwise neutral."""
    from market_causal_engine.learned.features import build_inference_features

    domain = str(result.get("domain") or (event or {}).get("domain") or "earnings")
    features = build_inference_features(result, event, domain=domain, with_earnings_interactions=True)
    domain_dir = str(domain_model.predict(features)["predicted_direction"])
    polarity_dir = _catalog_polarity_direction(result)
    if domain_dir == polarity_dir:
        return domain_dir
    return "neutral"


def infer_direction(
    result: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    learned: dict[str, Any] | None = None,
) -> str:
    """Predict simulated direction from kernel replay + learned domain models."""
    if learned is None:
        from market_causal_engine.learned.store import learned_available, load_learned_store

        store = load_learned_store() if learned_available() else {}
    else:
        store = learned
    is_catalog = str(result.get("replay_mode", "")).startswith("catalog_feed")

    domain = str(result.get("domain") or (event or {}).get("domain") or "earnings")
    if is_catalog:
        domain_model = store.get("catalog_domain_model")
        if domain_model is not None and _has_learned_features(result, event):
            try:
                return _catalog_consensus_direction(result, event=event, domain_model=domain_model)
            except Exception:  # noqa: BLE001
                pass

    risk = result.get("final_risk", {})
    pressure = float(risk.get("directional_pressure", 0.0))
    drawdown = float(risk.get("drawdown_risk", 0.0))
    replay_scale = float(result.get("replay_severity_scale", 1.0))

    if replay_scale < 0.3:
        if pressure >= 0.12 or drawdown >= 0.35:
            return "down"
        if pressure <= -0.05:
            return "up"
        return "neutral"

    if pressure >= 0.12 or drawdown >= 0.35:
        return "down"
    if pressure <= -0.05:
        return "up"

    trace_bias = _trace_pressure_bias(result.get("trace", []))
    if trace_bias >= 0.06:
        return "up"
    if trace_bias <= -0.06:
        return "down"

    polar = _scenario_polarity(event, pressure=pressure, drawdown=drawdown)
    if polar:
        return polar

    if is_catalog:
        model = store.get("catalog_domain_model")
    else:
        model = store.get("domain_models", {}).get(domain)

    if not is_catalog and model is not None and _has_learned_features(result, event):
        features = _features_from_result(result, event, domain)
        try:
            pred = model.predict(features)
            if pred.get("predicted_direction"):
                return str(pred["predicted_direction"])
        except Exception:  # noqa: BLE001
            pass

    return "neutral"


def _has_learned_features(result: dict[str, Any], event: dict[str, Any] | None) -> bool:
    claims = result.get("causal_claims", {}).get("accepted") if isinstance(result.get("causal_claims"), dict) else None
    if claims:
        return True
    if event and event.get("scenario_id"):
        return True
    return any(entry.get("action") == "commit" for entry in result.get("trace", []))


def _features_from_result(result: dict[str, Any], event: dict[str, Any] | None, domain: str) -> dict[str, float]:
    claims = result.get("causal_claims", {}).get("accepted") if isinstance(result.get("causal_claims"), dict) else None
    if claims:
        return build_case_features(claims=claims, trace=result.get("trace"), domain=domain)

    trace = result.get("trace", [])
    if trace and any(entry.get("action") == "commit" for entry in trace):
        return build_case_features(claims=[], trace=trace, domain=domain)

    if event and event.get("scenario_id"):
        return features_from_scenario_template(str(event["scenario_id"]), domain=domain)

    return build_case_features(claims=[], domain=domain)
