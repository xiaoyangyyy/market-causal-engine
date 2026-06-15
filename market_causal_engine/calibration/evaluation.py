"""Evaluate mechanism calibration against Phase 1 outcome anchors."""

from __future__ import annotations

import math
from typing import Any


def _direction(effect: float, *, band: float = 0.005) -> str:
    if effect < -band:
        return "down"
    if effect > band:
        return "up"
    return "neutral"


def evaluate_predictions(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"n": 0}

    abs_errors: list[float] = []
    sq_errors: list[float] = []
    dir_ok = 0
    dir_total = 0
    mech_agree = 0

    for rec in records:
        actual = float(rec.get("outcome_effect", rec.get("effect", 0.0)))
        pred = float(rec.get("predicted_effect", 0.0))
        abs_errors.append(abs(actual - pred))
        sq_errors.append((actual - pred) ** 2)

        actual_dir = _direction(actual)
        pred_dir = rec.get("predicted_direction", _direction(pred))
        if actual_dir != "neutral":
            dir_total += 1
            if pred_dir == actual_dir:
                dir_ok += 1

        if rec.get("dominant_mechanism") and rec.get("expected_dominant"):
            if rec["dominant_mechanism"] == rec["expected_dominant"]:
                mech_agree += 1

    n = len(records)
    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    return {
        "n": n,
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "direction_accuracy": round(dir_ok / dir_total, 4) if dir_total else None,
        "direction_evaluated": dir_total,
        "mechanism_match_rate": round(mech_agree / n, 4) if n else None,
    }


def leave_one_out_case_eval(
    cases: list[dict[str, Any]],
    *,
    fit_fn,
) -> dict[str, Any]:
    """LOO evaluation for case-study rows with {case_id, features, effect, domain}."""
    folds: list[dict[str, Any]] = []
    for holdout in cases:
        train = [c for c in cases if c["case_id"] != holdout["case_id"]]
        if len(train) < 3:
            continue
        model = fit_fn(train)
        pred = model.predict(holdout["features"])
        folds.append(
            {
                "case_id": holdout["case_id"],
                "outcome_effect": holdout["effect"],
                "predicted_effect": pred["predicted_effect"],
                "predicted_direction": pred["predicted_direction"],
                "confidence": pred["confidence"],
            }
        )
    metrics = evaluate_predictions(folds)
    return {"folds": folds, "metrics": metrics}
