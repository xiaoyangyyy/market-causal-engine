"""Shared lookahead-safe feature construction for learned inference."""

from __future__ import annotations

from typing import Any

from market_causal_engine.calibration.feature_builder import (
    build_case_features,
    expand_earnings_interactions,
    features_from_scenario_template,
)


def build_inference_features(
    result: dict[str, Any],
    event: dict[str, Any] | None,
    *,
    domain: str = "earnings",
    with_earnings_interactions: bool = False,
) -> dict[str, float]:
    claims = result.get("causal_claims", {}).get("accepted") if isinstance(result.get("causal_claims"), dict) else None
    if claims:
        feats = build_case_features(claims=claims, trace=result.get("trace"), domain=domain)
    else:
        trace = result.get("trace", [])
        if trace and any(entry.get("action") == "commit" for entry in trace):
            feats = build_case_features(claims=[], trace=trace, domain=domain)
        elif event and event.get("scenario_id"):
            feats = features_from_scenario_template(str(event["scenario_id"]), domain=domain)
        else:
            feats = build_case_features(claims=[], domain=domain)

    if with_earnings_interactions and domain == "earnings":
        return expand_earnings_interactions(feats)
    return feats
