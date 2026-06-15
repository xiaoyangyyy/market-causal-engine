"""Decide when catalog feed replay is high-confidence vs scenario fallback."""

from __future__ import annotations

from typing import Any

from market_causal_engine.evidence import MarketAtom

from market_causal_engine.benchmark.catalog.atoms import catalog_atom_summary


def catalog_signal_strength(
    result: dict[str, Any],
    *,
    atoms: list[MarketAtom] | None = None,
) -> float:
    """
    0–1 confidence that catalog replay should drive direction (lookahead-safe).

    High when kernel stress or atom polarity is clearly directional; low on mild filings.
    """
    risk = result.get("final_risk", {})
    pressure = float(risk.get("directional_pressure", 0.0))
    drawdown = float(risk.get("drawdown_risk", 0.0))
    summary = catalog_atom_summary(atoms or [])
    net = abs(float(summary.get("net_polarity", 0.0)))
    bull = float(summary.get("bull_total", 0.0))
    bear = float(summary.get("bear_total", 0.0))

    score = 0.0
    score += min(0.45, pressure * 0.9)
    score += min(0.25, drawdown * 0.7)
    score += min(0.2, net * 0.04)
    score += min(0.15, max(bull, bear) * 0.025)
    if bear >= 2 and bull <= 1:
        score += 0.12
    if bull >= 3 and bear <= 1:
        score += 0.10
    score -= min(0.2, float(summary.get("boilerplate_ratio", 0.0)) * 0.3)
    return round(max(0.0, min(1.0, score)), 4)


def should_use_catalog_feed(
    result: dict[str, Any],
    *,
    atoms: list[MarketAtom] | None = None,
    min_strength: float = 0.22,
) -> bool:
    return catalog_signal_strength(result, atoms=atoms) >= min_strength
