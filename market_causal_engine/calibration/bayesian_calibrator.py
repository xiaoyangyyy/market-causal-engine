"""Bayesian posterior over mechanism weights given Phase 1 effect anchor."""

from __future__ import annotations

import math
from typing import Any

from market_causal_engine.calibration.feature_builder import DOMAIN_SCENARIO_PRIORS, MECHANISM_BUCKETS


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    max_v = max(logits.values()) if logits else 0.0
    expd = {k: math.exp(v - max_v) for k, v in logits.items()}
    total = sum(expd.values()) or 1.0
    return {k: round(v / total, 4) for k, v in expd.items()}


def domain_prior(domain: str) -> dict[str, float]:
    priors = DOMAIN_SCENARIO_PRIORS.get(domain, DOMAIN_SCENARIO_PRIORS["earnings"])
    out = {k: priors.get(k, 0.05) for k in MECHANISM_BUCKETS}
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def calibrate_posterior(
    features: dict[str, float],
    *,
    observed_effect: float,
    domain: str,
    model_weights: dict[str, float] | None = None,
    sigma: float | None = None,
) -> dict[str, Any]:
    """
    Combine domain prior, claim/trace features, and Phase 1 effect into posterior mechanism weights.
    """
    prior = domain_prior(domain)
    sigma = sigma or max(0.02, min(0.12, abs(observed_effect) * 0.25 + 0.02))
    effect_mag = abs(observed_effect)
    effect_sign = -1.0 if observed_effect < 0 else (1.0 if observed_effect > 0 else 0.0)

    logits: dict[str, float] = {}
    for bucket in MECHANISM_BUCKETS:
        feat = float(features.get(f"m_{bucket}", 0.0))
        prior_w = float(prior.get(bucket, 0.05))
        model_w = float((model_weights or {}).get(bucket, feat))
        # Higher feature activation + model alignment increases posterior mass.
        logit = math.log(max(prior_w, 1e-6)) + 1.2 * feat + 0.8 * model_w
        logit += 0.35 * effect_sign * effect_mag * feat
        logits[bucket] = logit

    posterior = _softmax(logits)
    dominant = max(posterior, key=lambda k: posterior[k])

    # Posterior confidence: agreement between prior, features, and observed effect magnitude.
    agreement = sum(posterior[k] * float(features.get(f"m_{k}", 0.0)) for k in MECHANISM_BUCKETS)
    confidence = round(min(0.98, 0.4 + 0.35 * agreement + 0.2 * min(1.0, effect_mag / 0.2)), 3)

    return {
        "prior_weights": {k: round(prior[k], 4) for k in MECHANISM_BUCKETS},
        "posterior_weights": posterior,
        "dominant_mechanism": dominant,
        "posterior_confidence": confidence,
        "likelihood_sigma": round(sigma, 4),
        "observed_effect": round(observed_effect, 6),
    }
