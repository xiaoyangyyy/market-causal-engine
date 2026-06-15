"""Fit and export learned artifacts from Phase 1-3 data."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.analysis import MECHANISM_CATEGORIES
from market_causal_engine.calibration.domain_models import save_domain_models, save_earnings_magnitude_model, train_domain_models
from market_causal_engine.calibration.runner import build_training_samples, load_case_training_row
from market_causal_engine.case_study import list_case_studies, load_case_manifest
from market_causal_engine.scenarios import load_priors

LEARNED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "learned"
PRIORS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "priors"
CALIBRATION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "calibration"
BENCHMARK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"
COMPILER_RULES = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "compiler_rules" / "v0.1.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fit_kind_scales(cases: list[dict[str, Any]]) -> dict[str, float]:
    """Scale mechanism kinds from observed vs predicted effect ratio."""
    scales: dict[str, float] = {"*": 1.0}
    for row in cases:
        cal_path = Path(row["root"]) / "mechanism_calibration.json"
        if not cal_path.exists():
            continue
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        actual = float(cal.get("outcome_effect", 0.0))
        pred = float(cal.get("predicted_effect", 0.0))
        if abs(pred) < 1e-6:
            factor = 1.0
        else:
            factor = max(0.35, min(2.5, abs(actual) / abs(pred)))
        dom = str(cal.get("dominant_mechanism", "fundamental"))
        scales[dom] = round(scales.get(dom, 1.0) * 0.5 + factor * 0.5, 4)

    # Map dominant buckets to primary event kinds.
    bucket_to_kind = {
        "fundamental": "earnings_miss",
        "sentiment": "viral_negative_news",
        "liquidity": "liquidity_dry_up",
        "macro": "macro_rate_shock",
        "trust": "short_seller_report",
        "regulatory": "regulatory_probe",
    }
    kind_scales: dict[str, float] = {"*": 1.0}
    for bucket, scale in scales.items():
        if bucket == "*":
            continue
        kind = bucket_to_kind.get(bucket)
        if kind:
            kind_scales[kind] = scale
    return kind_scales


def _fit_severity_table() -> dict[str, float]:
    by_scenario: dict[str, list[float]] = {}
    for line in BENCHMARK_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        oc = rec.get("outcome_causal")
        if not oc:
            continue
        scenario = str(rec.get("scenario_id", "E1"))
        by_scenario.setdefault(scenario, []).append(abs(float(oc["effect"])))

    table: dict[str, float] = {}
    for scenario, vals in by_scenario.items():
        if vals:
            table[scenario] = round(min(0.98, statistics.median(vals) * 2.5), 3)

    # Case study anchors override.
    case_severity = {
        "earnings_miss": 0.85,
        "guidance_cut": 0.88,
        "short_seller_report": 0.82,
        "macro_rate_shock": 0.45,
        "cpi_surprise": 0.42,
        "liquidity_dry_up": 0.72,
        "viral_negative_news": 0.68,
    }
    table.update(case_severity)
    table["earnings"] = table.get("E1", 0.75)
    table["macro"] = table.get("X1", 0.4)
    return table


def _fit_compiler_weights() -> dict[str, float]:
    rules = json.loads(COMPILER_RULES.read_text(encoding="utf-8")).get("rules", [])
    weights: dict[str, float] = {}
    for rule in rules:
        kind = rule.get("event_kind", "")
        cat = MECHANISM_CATEGORIES.get(kind, "fundamental")
        base = {"fundamental": 0.72, "sentiment": 0.65, "liquidity": 0.6, "macro": 0.58, "regulatory": 0.62, "trust": 0.7}.get(cat, 0.55)
        weights[rule["rule_id"]] = round(base, 3)
    return weights


def _posterior_scale_for_kind(
    kind: str,
    domain_posteriors: dict[str, dict[str, float]],
) -> float:
    category = MECHANISM_CATEGORIES.get(kind)
    if not category:
        return 1.0

    best_rel = 1.0
    for posteriors in domain_posteriors.values():
        if not posteriors or category not in posteriors:
            continue
        mean_w = sum(float(v) for v in posteriors.values()) / max(len(posteriors), 1)
        rel = float(posteriors[category]) / max(mean_w, 1e-6)
        best_rel = max(best_rel, rel)
    return max(0.75, min(1.45, best_rel))


def _export_learned_priors(
    kind_scales: dict[str, float],
    domain_posteriors: dict[str, dict[str, float]],
) -> dict[str, Any]:
    base = load_priors(priors_profile="v0.1")
    out: dict[str, Any] = {}
    for kind, params in base.items():
        scaled = dict(params)
        kind_scale = float(kind_scales.get(kind, kind_scales.get("*", 1.0)))
        posterior_scale = _posterior_scale_for_kind(kind, domain_posteriors)
        scale = kind_scale * posterior_scale
        for key, val in list(scaled.items()):
            if key.endswith("_delta") or key.endswith("_relief") or key.endswith("_boost"):
                scaled[key] = round(float(val) * scale, 6)
        out[kind] = scaled
    out["_meta"] = {
        "source": "phase3_fit",
        "version": "v0.2_learned",
        "posterior_writeback": True,
    }
    return out


def _domain_posteriors_from_calibration() -> dict[str, dict[str, float]]:
    domains: dict[str, dict[str, float]] = {}
    for case in list_case_studies():
        path = Path(case.get("case_id", ""))  # wrong - need case root
        case_id = case["case_id"]
        cal_path = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies" / case_id / "mechanism_calibration.json"
        if not cal_path.exists():
            continue
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        domain = str(cal.get("domain", "earnings"))
        posteriors = cal.get("posterior_weights", {})
        if not posteriors:
            continue
        cur = domains.setdefault(domain, {})
        for bucket, weight in posteriors.items():
            cur[bucket] = round(cur.get(bucket, 0.0) * 0.5 + float(weight) * 0.5, 4)
    return domains


def fit_and_export_learned_stack(*, include_trace: bool = False) -> dict[str, Any]:
    LEARNED_DIR.mkdir(parents=True, exist_ok=True)

    samples = build_training_samples(include_trace=include_trace, major_only=True, case_weight=5)
    domain_models = train_domain_models(samples)
    save_domain_models(domain_models, LEARNED_DIR / "domain_models.json")
    if "earnings" in domain_models:
        save_earnings_magnitude_model(domain_models["earnings"], LEARNED_DIR / "earnings_magnitude.json")

    case_rows = []
    for case in list_case_studies():
        case_id = case["case_id"]
        manifest = load_case_manifest(case_id)
        row = load_case_training_row(case_id, include_trace=False)
        if row:
            row["root"] = manifest["_root"]
            case_rows.append(row)

    kind_scales = _fit_kind_scales(case_rows)
    (LEARNED_DIR / "kind_scales.json").write_text(
        json.dumps({"scales": kind_scales, "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    severity_table = _fit_severity_table()
    (LEARNED_DIR / "severity_table.json").write_text(
        json.dumps({"by_kind": severity_table, "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    rule_weights = _fit_compiler_weights()
    (LEARNED_DIR / "compiler_weights.json").write_text(
        json.dumps({"weights": rule_weights, "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    (LEARNED_DIR / "category_map.json").write_text(
        json.dumps({"map": dict(MECHANISM_CATEGORIES), "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    domain_posteriors = _domain_posteriors_from_calibration()
    (LEARNED_DIR / "domain_posteriors.json").write_text(
        json.dumps({"domains": domain_posteriors, "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    (LEARNED_DIR / "path_attention.json").write_text(
        json.dumps({"on_path": 0.65, "off_path": 0.35, "computed_at": _utc_now()}, indent=2), encoding="utf-8"
    )

    learned_priors = _export_learned_priors(kind_scales, domain_posteriors)
    PRIORS_DIR.mkdir(parents=True, exist_ok=True)
    (PRIORS_DIR / "mechanisms_v0.2_learned.json").write_text(
        json.dumps(learned_priors, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "domain_models": list(domain_models.keys()),
        "earnings_magnitude": str(LEARNED_DIR / "earnings_magnitude.json"),
        "training_samples": len(samples),
        "kind_scales": kind_scales,
        "severity_kinds": len(severity_table),
        "compiler_rules": len(rule_weights),
        "domain_posteriors": domain_posteriors,
        "priors_export": str(PRIORS_DIR / "mechanisms_v0.2_learned.json"),
        "computed_at": _utc_now(),
    }
    (LEARNED_DIR / "fit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
