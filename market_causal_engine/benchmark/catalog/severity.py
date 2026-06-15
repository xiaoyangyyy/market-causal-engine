"""Evidence-weighted severity scaling for catalog feed replay."""

from __future__ import annotations

from typing import Any

from market_causal_engine.benchmark.catalog.atoms import catalog_atom_summary
from market_causal_engine.evidence import MarketAtom


def catalog_replay_severity_scale(
    atoms: list[MarketAtom],
    *,
    risk: dict[str, Any] | None = None,
) -> float:
    """
    Derive replay severity scale from atom evidence only (no observed labels).

    Mild / mixed filings get down-weighted so neutral market days stay neutral.
    """
    summary = catalog_atom_summary(atoms)
    net = abs(float(summary["net_polarity"]))
    max_sev = float(summary["max_severity"])
    boiler = float(summary["boilerplate_ratio"])
    fin = int(summary["financial_atom_count"])

    scale = 0.35
    scale += min(0.25, abs(float(summary["net_polarity"])) * 0.06)
    scale += min(0.2, max_sev * 0.8)
    scale += min(0.1, fin * 0.02)
    scale -= min(0.25, boiler * 0.35)

    polar_abs = abs(float(summary["net_polarity"]))
    if polar_abs >= 3:
        scale = max(scale, 0.72)
    if polar_abs >= 5:
        scale = max(scale, 0.88)

    if risk:
        pressure = float(risk.get("directional_pressure", 0.0))
        drawdown = float(risk.get("drawdown_risk", 0.0))
        if pressure < 0.08 and drawdown < 0.15:
            scale *= 0.85

    return round(max(0.12, min(1.0, scale)), 4)
