"""Classify benchmark label quality for honest reporting."""

from __future__ import annotations

from market_causal_engine.benchmark.models import BenchmarkEvent

LabelTier = str  # real | proxy | placebo | unknown


def label_tier(event: BenchmarkEvent) -> LabelTier:
    """Tier used for headline vs appendix metrics."""
    if event.is_placebo:
        return "placebo"
    if event.uses_synthetic_labels:
        return "proxy"
    source = str(event.metadata.get("label_source", ""))
    if source in {"yahoo_daily", "case_study", "manual"}:
        return "real"
    if event.has_full_case or event.replay_mode == "case_study":
        return "real"
    if event.observed_outcomes.get("direction") is not None and not event.uses_synthetic_labels:
        if event.corpus in {"short_reports_public", "macro_releases", "company_shocks"}:
            return "real"
    return "unknown"


def is_real_label(event: BenchmarkEvent) -> bool:
    return label_tier(event) == "real"


def is_headline_eligible(event: BenchmarkEvent) -> bool:
    """Events suitable for README headline metrics."""
    tier = label_tier(event)
    return tier in {"real", "placebo"}
