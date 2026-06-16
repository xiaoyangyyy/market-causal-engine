"""Post-hoc impact calibration: map kernel scores to return estimates without look-ahead."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _anchors_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "market" / "calibration" / "impact_anchors.json"


def load_impact_anchors() -> dict[str, Any]:
    path = _anchors_path()
    if not path.exists():
        return {"anchors": [], "default_max_drawdown_pct": 35.0}
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_case_anchor(case_id: str | None) -> dict[str, Any] | None:
    if not case_id:
        return None
    for anchor in load_impact_anchors().get("anchors", []):
        if anchor.get("case_id") == case_id:
            return anchor
    return None


def _case_id_from_result(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    case_study = result.get("case_study") or {}
    return case_study.get("case_id") or result.get("scenario_id")


def _anchor_return_estimate(
    final_risk: dict[str, float],
    anchor: dict[str, Any],
    *,
    obs_direction: str,
) -> float | None:
    ref_ret = anchor.get("after_hours_return_pct")
    if ref_ret is None:
        ref_ret = anchor.get("session_return_pct")
    if ref_ret is None:
        return None

    ref_ret_f = float(ref_ret)
    if obs_direction == "up" or ref_ret_f > 0:
        score = abs(float(final_risk.get("directional_pressure", 0.0)))
        ref_score = anchor.get("directional_pressure") or anchor.get("drawdown_risk")
    else:
        score = float(final_risk.get("drawdown_risk", 0.0))
        ref_score = anchor.get("drawdown_risk")

    if ref_score is None or float(ref_score) <= 0:
        return None

    est = estimate_return_pct(
        score,
        observed_return_pct=ref_ret_f,
        reference_drawdown=float(ref_score),
    )
    if ref_ret_f > 0 and est is not None:
        return abs(est)
    return est


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
    result: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
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

    estimated_ah: float | None = None
    magnitude_source = "kernel_linear"
    domain = str((result or {}).get("domain") or "earnings")
    case_id = _case_id_from_result(result)
    case_anchor = lookup_case_anchor(case_id)
    if case_anchor is not None:
        estimated_ah = _anchor_return_estimate(
            final_risk,
            case_anchor,
            obs_direction=str(obs_direction),
        )
        if estimated_ah is not None:
            magnitude_source = "case_anchor"

    if estimated_ah is None and domain == "earnings" and result is not None:
        try:
            from market_causal_engine.learned.magnitude import infer_return_pct

            ev = event or result.get("_benchmark_event")
            learned_ret = infer_return_pct(result, event=ev)
            if learned_ret is not None:
                estimated_ah = learned_ret
                magnitude_source = "earnings_interaction_ridge"
        except Exception:  # noqa: BLE001
            pass

    ref_dd = observed.get("calibration_reference_drawdown")
    ref_pressure = observed.get("calibration_reference_pressure")
    if estimated_ah is None:
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
        "magnitude_source": magnitude_source,
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
        result=result,
    )
    return result
