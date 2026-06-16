"""Step B: channel ablation linked to marginal CAR contribution."""

from __future__ import annotations

from typing import Any

from market_causal_engine.benchmark.models import BenchmarkEvent

ABLATION_CHANNELS = ("no_news", "no_sec", "no_price")


def _infer_direction(result: dict[str, Any]) -> str:
    from market_causal_engine.benchmark.replay import infer_simulated_direction

    return infer_simulated_direction(result)


def predicted_return_pct(result: dict[str, Any]) -> float | None:
    """Model predicted after-hours return in percent."""
    cal = result.get("calibrated_impact") or {}
    est = cal.get("estimated_after_hours_return_pct")
    if est is not None:
        return float(est)
    pred = result.get("_predicted_effect")
    if pred is not None:
        return round(float(pred) * 100.0, 2)
    case = result.get("case_study") or {}
    sim = case.get("simulated_outcomes") or {}
    if sim.get("estimated_after_hours_return_pct") is not None:
        return float(sim["estimated_after_hours_return_pct"])
    return None


def observed_car_pct(outcome_causal: dict[str, Any] | None) -> float | None:
    if not outcome_causal:
        return None
    es = outcome_causal.get("event_study") or {}
    if es.get("CAR_pct") is not None:
        return float(es["CAR_pct"])
    if outcome_causal.get("effect") is not None:
        return round(float(outcome_causal["effect"]) * 100.0, 4)
    return None


def supports_car_ablation(event: BenchmarkEvent) -> bool:
    case_id = event.case_id or (event.event_id if event.replay_mode == "case_study" else None)
    if case_id:
        from pathlib import Path

        from market_causal_engine.case_study import load_case_manifest

        try:
            manifest = load_case_manifest(case_id)
            root = Path(manifest["_root"])
            atoms = root / manifest.get("atoms_path", "atoms.jsonl")
            return atoms.exists() and atoms.stat().st_size > 0
        except FileNotFoundError:
            return False
    if event.corpus == "earnings_sp500_2016_2025":
        from market_causal_engine.benchmark.catalog.replay import has_catalog_atoms

        return has_catalog_atoms(event.event_id)
    return False


def _replay_ablated(event: BenchmarkEvent, channel: str, *, until: int) -> dict[str, Any]:
    if event.replay_mode == "case_study" or event.case_id:
        from market_causal_engine.benchmark.replay import replay_case_study_event

        return replay_case_study_event(event, until=until, atom_filter=channel)
    from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event

    return replay_catalog_feed_event(event, until=until, atom_filter=channel)


def channel_contribution_row(
    *,
    channel: str,
    baseline_result: dict[str, Any],
    ablated_result: dict[str, Any],
    baseline_pred: float,
    observed_car: float,
) -> dict[str, Any]:
    ab_pred = predicted_return_pct(ablated_result)
    if ab_pred is None:
        return {}
    marginal = round(baseline_pred - ab_pred, 2)
    share = None
    if abs(observed_car) > 0.01:
        share = round(marginal / observed_car, 4)
    base_dir = _infer_direction(baseline_result)
    ab_dir = _infer_direction(ablated_result)
    base_path = list(baseline_result.get("dominant_causal_path") or baseline_result.get("dominant_path") or [])
    ab_path = list(ablated_result.get("dominant_causal_path") or ablated_result.get("dominant_path") or [])
    return {
        "channel": channel,
        "ablated_predicted_return_pct": ab_pred,
        "marginal_return_pct": marginal,
        "share_of_observed_car": share,
        "direction_flipped": base_dir != ab_dir,
        "path_changed": base_path != ab_path,
        "baseline_direction": base_dir,
        "ablated_direction": ab_dir,
    }


def run_car_ablation(
    event: BenchmarkEvent,
    baseline_result: dict[str, Any],
    *,
    until: int = 120,
    channels: tuple[str, ...] = ABLATION_CHANNELS,
) -> dict[str, Any] | None:
    """Ablate evidence channels and quantify marginal contribution vs observed CAR."""
    if not supports_car_ablation(event):
        return None

    oc = baseline_result.get("outcome_causal") or {}
    observed_car = observed_car_pct(oc)
    baseline_pred = predicted_return_pct(baseline_result)
    if observed_car is None or baseline_pred is None:
        return None

    channel_rows: dict[str, dict[str, Any]] = {}
    for channel in channels:
        try:
            ablated = _replay_ablated(event, channel, until=until)
        except (FileNotFoundError, ValueError, OSError):
            continue
        row = channel_contribution_row(
            channel=channel,
            baseline_result=baseline_result,
            ablated_result=ablated,
            baseline_pred=baseline_pred,
            observed_car=observed_car,
        )
        if row:
            channel_rows[channel] = row

    if not channel_rows:
        return None

    dominant_channel, dominant_row = max(
        channel_rows.items(),
        key=lambda kv: abs(kv[1].get("share_of_observed_car") or 0.0),
    )
    total_abs_share = sum(abs(r.get("share_of_observed_car") or 0.0) for r in channel_rows.values())

    return {
        "observed_car_pct": observed_car,
        "baseline_predicted_return_pct": baseline_pred,
        "channels": channel_rows,
        "dominant_channel": dominant_channel,
        "dominant_share_of_observed_car": dominant_row.get("share_of_observed_car"),
        "total_abs_share_of_observed_car": round(total_abs_share, 4),
        "n_channels": len(channel_rows),
    }


def attach_car_ablation(
    result: dict[str, Any],
    event: BenchmarkEvent | dict[str, Any],
    *,
    until: int = 120,
    channels: tuple[str, ...] = ABLATION_CHANNELS,
    force: bool = False,
) -> dict[str, Any]:
    """Attach car_ablation block under outcome_causal when atoms + CAR are available."""
    if isinstance(event, dict):
        ev = BenchmarkEvent.from_dict(event)
    else:
        ev = event

    oc = result.get("outcome_causal")
    if not isinstance(oc, dict):
        return result
    if oc.get("car_ablation") and not force:
        return result

    car = run_car_ablation(ev, result, until=until, channels=channels)
    if car:
        oc["car_ablation"] = car
        result["outcome_causal"] = oc
    return result


def should_run_car_ablation(event: BenchmarkEvent) -> bool:
    """Auto-run CAR ablation for case studies and full-case events only (avoid bulk cost)."""
    if event.is_placebo:
        return False
    if event.replay_mode == "case_study" or event.case_id:
        return True
    if event.has_full_case:
        return True
    return False
