"""Step B: attach econometric outcome layer to every replay result."""

from __future__ import annotations

import math
from typing import Any

from market_causal_engine.benchmark.models import BenchmarkEvent


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[idx]


def event_study_metrics(estimate: dict[str, Any]) -> dict[str, Any]:
    """CAR / AAR / t-stat / bootstrap CI from a counterfactual estimate."""
    effect = estimate.get("effect")
    if effect is None:
        return {}

    window_dates = list(estimate.get("event_window_dates") or [])
    n_days = max(1, len(window_dates))
    car = float(effect)
    aar = car / n_days

    pre_rmse = estimate.get("pre_fit_rmse")
    est_days = int(estimate.get("estimation_days") or 60)
    t_stat: float | None = None
    if pre_rmse is not None and float(pre_rmse) > 0:
        se = float(pre_rmse) / math.sqrt(max(est_days, 1))
        if se > 0:
            t_stat = round(car / se, 4)

    ci = confidence_interval(estimate, effect=car)

    return {
        "CAR": round(car, 6),
        "AAR": round(aar, 6),
        "CAR_pct": round(car * 100.0, 4),
        "AAR_pct": round(aar * 100.0, 4),
        "event_window_days": n_days,
        "t_stat": t_stat,
        "confidence_interval_95": ci,
        "placebo_rank": estimate.get("placebo_rank"),
        "placebo_n": estimate.get("placebo_n"),
    }


def confidence_interval(estimate: dict[str, Any], *, effect: float) -> dict[str, float] | None:
    """95% CI from placebo distribution or pre-fit RMSE normal approximation."""
    placebo_effects = estimate.get("placebo_effects")
    if isinstance(placebo_effects, list) and len(placebo_effects) >= 5:
        return {
            "low": round(_percentile(placebo_effects, 0.025), 6),
            "high": round(_percentile(placebo_effects, 0.975), 6),
            "method": "placebo_percentile",
        }

    pre_rmse = estimate.get("pre_fit_rmse")
    est_days = int(estimate.get("estimation_days") or 60)
    if pre_rmse is not None and float(pre_rmse) > 0:
        se = float(pre_rmse) / math.sqrt(max(est_days, 1))
        return {
            "low": round(effect - 1.96 * se, 6),
            "high": round(effect + 1.96 * se, 6),
            "method": "normal_approx_pre_rmse",
        }
    return None


def compact_estimate(estimate: dict[str, Any]) -> dict[str, Any]:
    """Strip heavy fields for corpus storage / API payloads."""
    out: dict[str, Any] = {
        "method": estimate.get("method"),
        "treated": estimate.get("treated"),
        "event_date": estimate.get("event_date"),
        "event_window": estimate.get("event_window"),
        "observed_return": estimate.get("observed_return"),
        "counterfactual_return": estimate.get("counterfactual_return"),
        "effect": estimate.get("effect"),
        "pre_fit_rmse": estimate.get("pre_fit_rmse"),
        "estimation_days": estimate.get("estimation_days"),
        "placebo_rank": estimate.get("placebo_rank"),
        "placebo_n": estimate.get("placebo_n"),
        "controls": estimate.get("controls") or estimate.get("factors"),
        "computed_at": estimate.get("computed_at"),
    }
    alternates = estimate.get("alternates") or {}
    alt_compact: dict[str, Any] = {}
    for name, alt in alternates.items():
        if isinstance(alt, dict) and "effect" in alt:
            alt_compact[name] = {
                "method": alt.get("method", name),
                "effect": alt.get("effect"),
                "observed_return": alt.get("observed_return"),
                "counterfactual_return": alt.get("counterfactual_return"),
                "pre_fit_rmse": alt.get("pre_fit_rmse"),
            }
    if alt_compact:
        out["alternates"] = alt_compact
    out["event_study"] = event_study_metrics(estimate)
    return {k: v for k, v in out.items() if v is not None}


def build_outcome_card(estimate: dict[str, Any]) -> dict[str, Any]:
    """Full outcome block for replay / event card API."""
    card = compact_estimate(estimate)
    factor_alt = (estimate.get("alternates") or {}).get("factor_model")
    if isinstance(factor_alt, dict):
        card["factor_adjusted_effect"] = factor_alt.get("effect")
    sc_alt = (estimate.get("alternates") or {}).get("synthetic_control")
    if isinstance(sc_alt, dict) and sc_alt.get("effect") is not None:
        card["synthetic_control_effect"] = sc_alt.get("effect")
    elif estimate.get("method") == "synthetic_control":
        card["synthetic_control_effect"] = estimate.get("effect")
    return card


def _method_for_event(event: BenchmarkEvent) -> str:
    if event.has_full_case or event.replay_mode == "case_study":
        return "synthetic_control"
    if event.corpus == "earnings_sp500_2016_2025":
        return "abnormal_return"
    return "auto"


def _should_run_placebo(event: BenchmarkEvent, run_placebo: bool | None) -> bool:
    if run_placebo is not None:
        return run_placebo
    return bool(event.has_full_case or event.replay_mode == "case_study")


def resolve_outcome_causal(
    event: BenchmarkEvent,
    *,
    method: str | None = None,
    run_placebo: bool | None = None,
    force_estimate: bool = False,
    include_alternates: bool | None = None,
) -> dict[str, Any] | None:
    """Resolve econometric outcome for an event (cached corpus → live estimate)."""
    if event.is_placebo:
        return {"method": "none", "reason": "placebo_control_event"}

    if event.outcome_causal and not force_estimate:
        cached = dict(event.outcome_causal)
        if "event_study" not in cached:
            cached["event_study"] = event_study_metrics(cached)
        return cached

    if event.uses_synthetic_labels:
        return {"method": "unavailable", "reason": "proxy_label_event"}

    if not event.ticker or not event.event_date:
        return None

    from market_causal_engine.counterfactuals.estimate import estimate_outcome_causal

    chosen = method or _method_for_event(event)
    prefer_sc = chosen == "synthetic_control"
    alt = include_alternates if include_alternates is not None else prefer_sc

    try:
        full = estimate_outcome_causal(
            event.ticker,
            event.event_date,
            method=chosen,  # type: ignore[arg-type]
            prefer_sc=prefer_sc,
            run_placebo=_should_run_placebo(event, run_placebo),
            include_alternates=alt,
        )
        return build_outcome_card(full)
    except Exception as exc:  # noqa: BLE001
        return {"method": "unavailable", "error": str(exc), "treated": event.ticker.upper()}


def attach_outcome_causal(
    result: dict[str, Any],
    event: BenchmarkEvent | dict[str, Any] | None,
    *,
    method: str | None = None,
    run_placebo: bool | None = None,
    force_estimate: bool = False,
    car_ablation: bool | None = None,
    until: int = 120,
) -> dict[str, Any]:
    """Attach mandatory outcome_causal block to a replay result."""
    if event is None:
        return result

    if isinstance(event, dict):
        ev = BenchmarkEvent.from_dict(event)
    else:
        ev = event

    if result.get("outcome_causal") and not force_estimate:
        oc_existing = result["outcome_causal"]
    else:
        oc_existing = None

    # Case study manifest may already be on result via run_case_study
    manifest_oc = None
    case = result.get("case_study") or {}
    if isinstance(case, dict):
        manifest_oc = case.get("outcome_causal")

    if manifest_oc and not force_estimate and not oc_existing:
        card = dict(manifest_oc)
        if "event_study" not in card:
            card["event_study"] = event_study_metrics(card)
        result["outcome_causal"] = card
    elif not oc_existing:
        outcome = resolve_outcome_causal(
            ev,
            method=method,
            run_placebo=run_placebo,
            force_estimate=force_estimate,
        )
        if outcome is not None:
            result["outcome_causal"] = outcome

    run_car = car_ablation
    if run_car is None:
        from market_causal_engine.counterfactuals.car_ablation import should_run_car_ablation

        run_car = should_run_car_ablation(ev)
    if run_car and result.get("outcome_causal"):
        from market_causal_engine.counterfactuals.car_ablation import attach_car_ablation

        attach_car_ablation(result, ev, until=until)
    return result


def build_event_card(result: dict[str, Any], *, event: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured event card: path + econometric outcome + provenance hooks."""
    ev = event or result.get("_benchmark_event") or {}
    card: dict[str, Any] = {
        "event_id": result.get("benchmark_event_id") or ev.get("event_id"),
        "ticker": ev.get("ticker"),
        "event_date": ev.get("event_date"),
        "domain": result.get("domain") or ev.get("domain"),
        "replay_mode": result.get("replay_mode"),
        "dominant_path": result.get("dominant_causal_path") or result.get("dominant_path") or [],
        "simulated_direction": result.get("simulated_direction"),
        "observed_direction": result.get("observed_direction") or (ev.get("observed_outcomes") or {}).get("direction"),
        "outcome_causal": result.get("outcome_causal"),
        "car_ablation_dominant_channel": (
            (result.get("outcome_causal") or {}).get("car_ablation") or {}
        ).get("dominant_channel"),
        "calibrated_impact": result.get("calibrated_impact"),
        "causal_claims_summary": _claims_summary(result),
        "router_preferred": result.get("router_preferred"),
        "catalog_fallback": result.get("catalog_fallback"),
    }
    return {k: v for k, v in card.items() if v is not None}


def _claims_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    raw = result.get("causal_claims")
    if not isinstance(raw, dict):
        return None
    accepted = raw.get("accepted") or []
    return {
        "claim_count": len(accepted),
        "catalog_net_polarity": raw.get("catalog_net_polarity"),
        "catalog_quality_score": raw.get("catalog_quality_score"),
        "llm_proposer": raw.get("llm_proposer"),
    }
