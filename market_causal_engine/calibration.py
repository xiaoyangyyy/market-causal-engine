"""Post-hoc impact calibration: map kernel scores to return estimates without look-ahead."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.constants import OUTCOME_DISPLAY, OUTCOME_KEYS


def _anchors_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "market" / "calibration" / "impact_anchors.json"


def load_impact_anchors() -> dict[str, Any]:
    path = _anchors_path()
    if not path.exists():
        return {"anchors": [], "default_max_drawdown_pct": 35.0}
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_return_pct(
    drawdown_risk: float,
    *,
    observed_return_pct: float | None = None,
    reference_drawdown: float | None = None,
) -> float | None:
    """
    Linear scale from kernel drawdown_risk to estimated return %.
    Uses case-specific anchor when provided; otherwise global default.
    """
    if drawdown_risk <= 0:
        return 0.0
    anchors = load_impact_anchors()
    ref_dd = reference_drawdown or anchors.get("reference_drawdown_at_full", 0.72)
    ref_ret = observed_return_pct
    if ref_ret is None:
        ref_ret = -float(anchors.get("default_max_drawdown_pct", 35.0))
    if ref_dd <= 0:
        return None
    scale = abs(ref_ret) / ref_dd
    sign = -1.0 if ref_ret < 0 else 1.0
    return round(sign * drawdown_risk * scale, 2)


def calibrate_final_risk(
    final_risk: dict[str, float],
    *,
    observed_outcomes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach calibrated return/volatility estimates (post-hoc labels only)."""
    observed = observed_outcomes or {}
    obs_direction = observed.get("direction", "down")
    dd = float(final_risk.get("drawdown_risk", 0.0))
    pressure = abs(float(final_risk.get("directional_pressure", 0.0)))
    obs_ah = observed.get("after_hours_return_pct")
    if obs_ah is None:
        obs_ah = observed.get("session_return_pct")
    obs_2d = observed.get("two_day_return_pct")

    ref_dd = observed.get("calibration_reference_drawdown")
    ref_pressure = observed.get("calibration_reference_pressure")
    if obs_direction == "up":
        score = pressure
        ref_score = float(ref_pressure or ref_dd or 0.55)
    else:
        score = dd
        ref_score = float(ref_dd) if ref_dd is not None else None
        if ref_score is None and obs_ah is not None:
            ref_score = 0.72

    estimated_ah = estimate_return_pct(
        score,
        observed_return_pct=float(obs_ah) if obs_ah is not None else None,
        reference_drawdown=ref_score,
    )
    if estimated_ah is not None and obs_direction == "up" and obs_ah is not None and float(obs_ah) > 0:
        estimated_ah = abs(estimated_ah)

    out: dict[str, Any] = {
        "raw": dict(final_risk),
        "estimated_after_hours_return_pct": estimated_ah,
    }

    if obs_ah is not None and estimated_ah is not None:
        out["after_hours_error_pct"] = round(abs(estimated_ah - float(obs_ah)), 2)
        out["after_hours_within_band"] = out["after_hours_error_pct"] <= 8.0

    if obs_2d is not None and estimated_ah is not None:
        out["estimated_two_day_return_pct"] = round(estimated_ah * 1.35, 2)
        out["two_day_error_pct"] = round(abs(out["estimated_two_day_return_pct"] - float(obs_2d)), 2)

    vol = final_risk.get("volatility_risk", 0.0)
    out["estimated_realized_vol_multiplier"] = round(1.0 + vol * 1.5, 3)

    return out


def attach_calibration(result: dict[str, Any], observed: dict[str, Any] | None = None) -> dict[str, Any]:
    observed = observed or result.get("case_study", {}).get("observed_outcomes", {})
    result["calibrated_impact"] = calibrate_final_risk(
        result.get("final_risk", {}),
        observed_outcomes=observed,
    )
    return result
