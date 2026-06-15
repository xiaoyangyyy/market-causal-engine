"""Build mechanism feature vectors from Phase 2 claims, kernel trace, and benchmark metadata."""

from __future__ import annotations

from typing import Any

from market_causal_engine.analysis import compute_mechanism_contributions

MECHANISM_BUCKETS = (
    "fundamental",
    "sentiment",
    "liquidity",
    "macro",
    "regulatory",
    "trust",
)

MAGNITUDE_ORD = {"none": 0.0, "small": 0.25, "medium": 0.5, "large": 1.0}

DOMAIN_SCENARIO_PRIORS: dict[str, dict[str, float]] = {
    "earnings": {"fundamental": 0.45, "sentiment": 0.25, "liquidity": 0.2, "macro": 0.1},
    "short_report": {"trust": 0.35, "sentiment": 0.25, "liquidity": 0.2, "regulatory": 0.2},
    "macro": {"macro": 0.55, "liquidity": 0.2, "sentiment": 0.15, "fundamental": 0.1},
}


def zero_mechanism_features() -> dict[str, float]:
    return {f"m_{k}": 0.0 for k in MECHANISM_BUCKETS}


def features_from_claims(claims: list[dict[str, Any]]) -> dict[str, float]:
    feats = zero_mechanism_features()
    if not claims:
        return feats

    severities: list[float] = []
    confidences: list[float] = []
    for claim in claims:
        mech = str(claim.get("mechanism", "")).lower()
        if mech not in MECHANISM_BUCKETS:
            continue
        weight = float(claim.get("severity", 0.0)) * float(claim.get("confidence", 1.0))
        feats[f"m_{mech}"] += weight
        severities.append(float(claim.get("severity", 0.0)))
        confidences.append(float(claim.get("confidence", 1.0)))

    total = sum(feats[f"m_{k}"] for k in MECHANISM_BUCKETS) or 1.0
    for key in list(feats):
        if key.startswith("m_"):
            feats[key] = round(feats[key] / total, 4)

    feats["claim_count"] = float(len(claims))
    feats["max_severity"] = round(max(severities) if severities else 0.0, 4)
    feats["mean_confidence"] = round(sum(confidences) / len(confidences) if confidences else 0.0, 4)
    return feats


def features_from_trace(
    trace: list[dict[str, Any]],
    *,
    dominant_path: list[str] | None = None,
) -> dict[str, float]:
    contrib = compute_mechanism_contributions(trace, dominant_path=dominant_path or [], path_weighted=True)
    feats = zero_mechanism_features()
    for bucket in MECHANISM_BUCKETS:
        feats[f"m_{bucket}"] = round(float(contrib.get(bucket, 0.0)), 4)
    feats["trace_total"] = round(sum(feats[f"m_{k}"] for k in MECHANISM_BUCKETS), 4)
    return feats


def features_from_scenario_template(scenario_id: str, *, domain: str = "earnings") -> dict[str, float]:
    """Scenario priors only — no observed_outcomes (lookahead-safe for simulated direction)."""
    raw = features_from_benchmark_record(
        {
            "domain": domain,
            "scenario_id": scenario_id,
            "observed_outcomes": {},
            "labels": {},
        }
    )
    return {key: raw[key] for key in FEATURE_ORDER if key in raw}


def features_from_benchmark_record(record: dict[str, Any]) -> dict[str, float]:
    domain = str(record.get("domain", "earnings"))
    priors = DOMAIN_SCENARIO_PRIORS.get(domain, DOMAIN_SCENARIO_PRIORS["earnings"])
    feats = zero_mechanism_features()
    for bucket, weight in priors.items():
        feats[f"m_{bucket}"] = weight

    scenario = str(record.get("scenario_id", "E1"))
    if scenario == "E1":
        feats["m_fundamental"] = min(1.0, feats["m_fundamental"] + 0.15)
        feats["m_sentiment"] = min(1.0, feats["m_sentiment"] + 0.1)
    elif scenario == "E2":
        feats["m_sentiment"] = min(1.0, feats["m_sentiment"] + 0.15)
        feats["m_liquidity"] = min(1.0, feats["m_liquidity"] + 0.1)

    obs = record.get("observed_outcomes", {})
    direction = str(obs.get("direction", "neutral"))
    feats["direction_sign"] = -1.0 if direction == "down" else (1.0 if direction == "up" else 0.0)
    labels = record.get("labels", {})
    feats["is_major"] = 1.0 if labels.get("is_major_event") else 0.0
    feats["magnitude_ord"] = MAGNITUDE_ORD.get(str(obs.get("magnitude_bucket", "none")), 0.0)
    feats["claim_count"] = 0.0
    # Lookahead-safe training default: scenario severity prior, not observed magnitude bucket.
    if scenario == "E2":
        feats["max_severity"] = 0.55
    else:
        feats["max_severity"] = 0.65 if feats["is_major"] else 0.45
    feats["mean_confidence"] = 0.5 + 0.5 * feats["is_major"]
    return feats


# Model features only (exclude label-leaky benchmark fields like direction_sign).
FEATURE_ORDER = [
    *[f"m_{k}" for k in MECHANISM_BUCKETS],
    "max_severity",
    "mean_confidence",
    "trace_total",
]

EARNINGS_INTERACTION_ORDER = [
    "x_fund_sent",
    "x_fund_liq",
    "x_sent_liq",
    "x_fund_sev",
    "x_sent_trace",
    "x_fund_macro",
]


def expand_earnings_interactions(features: dict[str, float]) -> dict[str, float]:
    """Polynomial interaction terms for earnings magnitude (ridge-friendly)."""
    out = dict(features)
    f = float(features.get("m_fundamental", 0.0))
    s = float(features.get("m_sentiment", 0.0))
    l = float(features.get("m_liquidity", 0.0))
    m = float(features.get("m_macro", 0.0))
    sev = float(features.get("max_severity", 0.0))
    tr = float(features.get("trace_total", 0.0))
    out["x_fund_sent"] = round(f * s, 6)
    out["x_fund_liq"] = round(f * l, 6)
    out["x_sent_liq"] = round(s * l, 6)
    out["x_fund_sev"] = round(f * sev, 6)
    out["x_sent_trace"] = round(s * tr, 6)
    out["x_fund_macro"] = round(f * m, 6)
    return out


EARNINGS_FEATURE_ORDER = [*FEATURE_ORDER, *EARNINGS_INTERACTION_ORDER]


def merge_feature_dicts(*parts: dict[str, float], weights: list[float] | None = None) -> dict[str, float]:
    if not parts:
        return {}
    weights = weights or [1.0] * len(parts)
    keys = sorted({k for p in parts for k in p})
    out: dict[str, float] = {}
    denom = sum(weights) or 1.0
    max_keys = {"claim_count", "max_severity", "trace_total"}
    for key in keys:
        vals = [p.get(key, 0.0) for p in parts]
        if key in max_keys:
            out[key] = round(max(vals), 4)
        else:
            out[key] = round(sum(v * w for v, w in zip(vals, weights, strict=True)) / denom, 4)
    return out


def build_case_features(
    *,
    claims: list[dict[str, Any]] | None = None,
    trace: list[dict[str, Any]] | None = None,
    dominant_path: list[str] | None = None,
    domain: str = "earnings",
) -> dict[str, float]:
    claim_feats = features_from_claims(claims or [])
    if trace:
        trace_feats = features_from_trace(trace, dominant_path=dominant_path)
        merged = merge_feature_dicts(claim_feats, trace_feats, weights=[0.65, 0.35])
    else:
        merged = claim_feats

    priors = DOMAIN_SCENARIO_PRIORS.get(domain, DOMAIN_SCENARIO_PRIORS["earnings"])
    for bucket, prior in priors.items():
        key = f"m_{bucket}"
        merged[key] = round(0.7 * merged.get(key, 0.0) + 0.3 * prior, 4)
    return merged


METADATA_FEATURE_ORDER = [
    *FEATURE_ORDER,
    "claim_count",
    "direction_sign",
    "is_major",
    "magnitude_ord",
]


def vectorize(features: dict[str, float], *, feature_order: list[str] | None = None) -> list[float]:
    order = feature_order or FEATURE_ORDER
    return [float(features.get(name, 0.0)) for name in order]
