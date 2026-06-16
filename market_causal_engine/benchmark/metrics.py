"""Benchmark metrics: direction, calibration, placebo, confidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_causal_engine.benchmark.label_quality import label_tier as event_label_tier
from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.replay import infer_simulated_direction


@dataclass
class EventScore:
    event_id: str
    corpus: str
    domain: str
    observed_direction: str | None
    simulated_direction: str | None
    direction_match: bool | None
    drawdown_risk: float = 0.0
    directional_pressure: float = 0.0
    calibration_error_pct: float | None = None
    is_placebo: bool = False
    false_positive: bool = False
    is_major_event: bool = True
    synthetic_labels: bool = False
    label_tier: str = "unknown"
    router_preferred: str | None = None
    used_catalog_path: bool = False
    dominant_path: list[str] = field(default_factory=list)
    replay_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "corpus": self.corpus,
            "domain": self.domain,
            "observed_direction": self.observed_direction,
            "simulated_direction": self.simulated_direction,
            "direction_match": self.direction_match,
            "drawdown_risk": self.drawdown_risk,
            "directional_pressure": self.directional_pressure,
            "calibration_error_pct": self.calibration_error_pct,
            "is_placebo": self.is_placebo,
            "false_positive": self.false_positive,
            "is_major_event": self.is_major_event,
            "synthetic_labels": self.synthetic_labels,
            "label_tier": self.label_tier,
            "router_preferred": self.router_preferred,
            "used_catalog_path": self.used_catalog_path,
            "dominant_path": self.dominant_path,
            "replay_mode": self.replay_mode,
        }


def score_event(
    event: BenchmarkEvent,
    result: dict[str, Any],
    *,
    placebo_drawdown_threshold: float = 0.35,
    placebo_pressure_threshold: float = 0.20,
) -> EventScore:
    risk = result.get("final_risk", {})
    dd = float(risk.get("drawdown_risk", 0.0))
    pressure = float(risk.get("directional_pressure", 0.0))

    obs_dir = event.observed_outcomes.get("direction")
    is_major = bool(event.labels.get("is_major_event", True))
    aligned = result.get("aligned_observed_outcomes")
    if aligned and aligned.get("direction"):
        obs_dir = aligned.get("direction")
        ret = aligned.get("after_hours_return_pct")
        if ret is not None:
            is_major = abs(float(ret)) >= 3.0
    elif result.get("observed_direction"):
        obs_dir = result.get("observed_direction")
    if obs_dir is None and event.is_placebo:
        obs_dir = "neutral"

    sim_dir = result.get("simulated_direction")
    if sim_dir is None:
        case = result.get("case_study", {})
        sim_dir = case.get("simulated_outcomes", {}).get("direction")
    if sim_dir is None:
        sim_dir = infer_simulated_direction(result)

    direction_match = None
    if obs_dir and obs_dir != "unknown":
        if obs_dir == "neutral":
            direction_match = sim_dir == "neutral"
        else:
            direction_match = sim_dir == obs_dir

    cal = result.get("calibrated_impact", {})
    cal_err = cal.get("after_hours_error_pct")
    if cal_err is None and event.observed_outcomes.get("after_hours_return_pct") is not None:
        est = cal.get("estimated_after_hours_return_pct")
        obs = event.observed_outcomes.get("after_hours_return_pct")
        if est is not None and obs is not None:
            cal_err = abs(float(est) - float(obs))

    false_positive = False
    if event.is_placebo:
        false_positive = dd >= placebo_drawdown_threshold or abs(pressure) >= placebo_pressure_threshold

    path = result.get("dominant_causal_path") or result.get("dominant_path") or []
    replay_mode = str(result.get("replay_mode", event.replay_mode))
    used_catalog = replay_mode.startswith("catalog_feed") and not bool(result.get("catalog_fallback"))
    router_pref = result.get("router_preferred")
    if router_pref is None:
        router_pref = "catalog" if used_catalog else "scenario"

    return EventScore(
        event_id=event.event_id,
        corpus=event.corpus,
        domain=event.domain,
        observed_direction=str(obs_dir) if obs_dir else None,
        simulated_direction=sim_dir,
        direction_match=direction_match,
        drawdown_risk=dd,
        directional_pressure=pressure,
        calibration_error_pct=float(cal_err) if cal_err is not None else None,
        is_placebo=event.is_placebo,
        false_positive=false_positive,
        is_major_event=is_major,
        synthetic_labels=event.uses_synthetic_labels,
        label_tier=event_label_tier(event),
        router_preferred=str(router_pref) if router_pref else None,
        used_catalog_path=used_catalog,
        dominant_path=list(path),
        replay_mode=replay_mode,
    )


def _direction_accuracy(scores: list[EventScore]) -> float | None:
    scored = [s for s in scores if s.direction_match is not None]
    if not scored:
        return None
    return sum(1 for s in scored if s.direction_match) / len(scored)


def naive_baselines(scores: list[EventScore], *, label_tier: str = "real") -> dict[str, Any]:
    """Naive baselines on a label tier subset."""
    from collections import Counter

    subset = [s for s in scores if s.label_tier == label_tier and s.direction_match is not None]
    if not subset:
        return {}
    obs = [str(s.observed_direction) for s in subset]
    counts = Counter(obs)
    majority = counts.most_common(1)[0][0]
    n = len(subset)
    return {
        "n": n,
        "always_neutral_accuracy": round(sum(1 for o in obs if o == "neutral") / n, 4),
        "always_majority_class_accuracy": round(counts[majority] / n, 4),
        "majority_class": majority,
        "class_distribution": dict(counts),
    }


def select_failed_cases(
    scores: list[EventScore],
    *,
    label_tier: str = "real",
    n: int = 10,
) -> list[dict[str, Any]]:
    """Top direction mismatches for public failure appendix."""
    mismatches = [
        s
        for s in scores
        if s.label_tier == label_tier and s.direction_match is False and not s.is_placebo
    ]
    mismatches.sort(key=lambda s: (s.drawdown_risk, abs(s.directional_pressure)), reverse=True)
    out: list[dict[str, Any]] = []
    for s in mismatches[:n]:
        out.append(
            {
                "event_id": s.event_id,
                "corpus": s.corpus,
                "observed_direction": s.observed_direction,
                "simulated_direction": s.simulated_direction,
                "replay_mode": s.replay_mode,
                "router_preferred": s.router_preferred,
                "used_catalog_path": s.used_catalog_path,
                "drawdown_risk": round(s.drawdown_risk, 4),
                "dominant_path": " → ".join(s.dominant_path[:5]),
            }
        )
    return out


def build_headline_summary(scores: list[EventScore]) -> dict[str, Any]:
    """Real-label headline metrics — never mix proxy labels into primary table."""
    real = [s for s in scores if s.label_tier == "real"]
    placebo = [s for s in scores if s.label_tier == "placebo"]
    proxy = [s for s in scores if s.label_tier == "proxy"]

    by_corpus: dict[str, dict[str, Any]] = {}
    for s in real:
        bucket = by_corpus.setdefault(s.corpus, [])
        bucket.append(s)
    by_corpus_stats = {
        corpus: {
            "n": len(sub),
            "direction_accuracy": _direction_accuracy(sub),
        }
        for corpus, sub in by_corpus.items()
    }

    catalog_path = [s for s in real if s.used_catalog_path]
    scenario_path = [s for s in real if not s.used_catalog_path and not s.is_placebo]

    return {
        "real_label_n": len(real),
        "real_label_direction_accuracy": _direction_accuracy(real),
        "placebo_n": len(placebo),
        "placebo_false_positive_rate": (
            sum(1 for s in placebo if s.false_positive) / len(placebo) if placebo else None
        ),
        "proxy_label_n": len(proxy),
        "by_corpus_real_label": by_corpus_stats,
        "real_label_catalog_path_n": len(catalog_path),
        "real_label_catalog_path_direction_accuracy": _direction_accuracy(catalog_path),
        "real_label_scenario_router_path_n": len(scenario_path),
        "real_label_scenario_router_path_direction_accuracy": _direction_accuracy(scenario_path),
        "naive_baselines_real_label": naive_baselines(scores, label_tier="real"),
        "warning": "Do not use mixed-corpus overall accuracy as headline; see appendix.",
    }


def build_appendix_summary(scores: list[EventScore]) -> dict[str, Any]:
    """Mixed metrics kept for regression tracking — not for external headline."""
    return {
        "mixed_overall_direction_accuracy": _direction_accuracy(scores),
        "mixed_n": len([s for s in scores if s.direction_match is not None]),
        "note": (
            "Inflated when earnings router defaults to scenario templates (E1/E2). "
            "Use headline.real_label_* and catalog_only instead."
        ),
        "by_corpus_all_labels": aggregate_scores(scores).get("by_corpus"),
    }


def aggregate_scores(scores: list[EventScore]) -> dict[str, Any]:
    if not scores:
        return {"count": 0}

    dir_scored = [s for s in scores if s.direction_match is not None]
    dir_acc = sum(1 for s in dir_scored if s.direction_match) / len(dir_scored) if dir_scored else None

    placebo = [s for s in scores if s.is_placebo]
    fp_rate = sum(1 for s in placebo if s.false_positive) / len(placebo) if placebo else None

    cal_errors = [s.calibration_error_pct for s in scores if s.calibration_error_pct is not None and not s.synthetic_labels]
    real_cal = [s.calibration_error_pct for s in scores if s.calibration_error_pct is not None and not s.synthetic_labels and not s.is_placebo]
    mean_cal = sum(cal_errors) / len(cal_errors) if cal_errors else None
    mean_cal_real = sum(real_cal) / len(real_cal) if real_cal else None

    by_corpus: dict[str, dict[str, Any]] = {}
    for s in scores:
        bucket = by_corpus.setdefault(s.corpus, {"scores": []})
        bucket["scores"].append(s)
    for corpus, bucket in by_corpus.items():
        sub = bucket["scores"]
        sub_dir = [x for x in sub if x.direction_match is not None]
        bucket["n"] = len(sub)
        bucket["direction_accuracy"] = (
            sum(1 for x in sub_dir if x.direction_match) / len(sub_dir) if sub_dir else None
        )
        bucket["placebo_fp_rate"] = (
            sum(1 for x in sub if x.false_positive) / len([x for x in sub if x.is_placebo])
            if any(x.is_placebo for x in sub)
            else None
        )
        del bucket["scores"]

    return {
        "count": len(scores),
        "direction_accuracy": dir_acc,
        "direction_scored": len(dir_scored),
        "placebo_false_positive_rate": fp_rate,
        "placebo_count": len(placebo),
        "mean_calibration_error_pct": mean_cal,
        "mean_calibration_error_real_cases_pct": mean_cal_real,
        "by_corpus": by_corpus,
    }


def split_by_date(
    scores: list[EventScore],
    events: list[BenchmarkEvent],
    *,
    cutoff_date: str,
) -> tuple[list[EventScore], list[EventScore]]:
    by_id = {e.event_id: e for e in events}
    train, test = [], []
    for s in scores:
        ev = by_id.get(s.event_id)
        if ev and ev.event_date < cutoff_date:
            train.append(s)
        else:
            test.append(s)
    return train, test


def oot_accuracy(
    train: list[EventScore],
    test: list[EventScore],
    *,
    label_tier: str | None = None,
) -> dict[str, Any]:
    if label_tier:
        train = [s for s in train if s.label_tier == label_tier]
        test = [s for s in test if s.label_tier == label_tier]

    return {
        "cutoff_used": True,
        "label_tier_filter": label_tier,
        "train_n": len(train),
        "test_n": len(test),
        "train_direction_accuracy": _direction_accuracy(train),
        "test_direction_accuracy": _direction_accuracy(test),
    }


def confidence_stability(scores: list[EventScore]) -> dict[str, Any]:
    """High drawdown risk events should have lower calibration variance (proxy for confidence)."""
    high = [s for s in scores if s.drawdown_risk >= 0.5 and s.calibration_error_pct is not None]
    low = [s for s in scores if s.drawdown_risk < 0.3 and s.calibration_error_pct is not None]
    def mean_err(sub: list[EventScore]) -> float | None:
        if not sub:
            return None
        return sum(s.calibration_error_pct for s in sub if s.calibration_error_pct is not None) / len(sub)

    return {
        "high_risk_mean_cal_error": mean_err(high),
        "low_risk_mean_cal_error": mean_err(low),
        "high_risk_n": len(high),
        "low_risk_n": len(low),
    }
