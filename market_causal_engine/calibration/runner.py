"""Train and apply mechanism calibration (Phase 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.calibration.bayesian_calibrator import calibrate_posterior
from market_causal_engine.calibration.evaluation import evaluate_predictions, leave_one_out_case_eval
from market_causal_engine.calibration.feature_builder import (
    build_case_features,
    features_from_benchmark_record,
)
from market_causal_engine.calibration.mechanism_model import (
    MechanismModel,
    TrainingSample,
    default_model_path,
    load_model,
    save_model,
)
from market_causal_engine.case_study import list_case_studies, load_case_manifest, run_case_study

CASE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies"
BENCHMARK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "earnings_sp500_2016_2025.jsonl"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "calibration"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _case_domain(manifest: dict[str, Any]) -> str:
    domain = str(manifest.get("domain", manifest.get("event_type", "earnings")))
    return {
        "short_squeeze": "short_report",
        "short_report": "short_report",
        "fomc": "macro",
        "cpi": "macro",
    }.get(domain, domain if domain in ("earnings", "short_report", "macro") else "earnings")


def load_case_training_row(case_id: str, *, include_trace: bool = True) -> dict[str, Any] | None:
    root = CASE_ROOT / case_id
    manifest = load_case_manifest(case_id)
    outcome = _load_json(root / "outcome_causal.json")
    if outcome is None or "effect" not in outcome:
        return None

    claims_doc = _load_json(root / "causal_claims.json")
    claims = list((claims_doc or {}).get("accepted", []))

    trace: list[dict[str, Any]] = []
    dominant_path: list[str] = []
    if include_trace:
        replay = run_case_study(case_id, as_of=int(manifest.get("default_until", 120)))
        trace = replay.get("trace", [])
        dominant_path = replay.get("dominant_causal_path", [])

    domain = _case_domain(manifest)
    features = build_case_features(
        claims=claims,
        trace=trace or None,
        dominant_path=dominant_path,
        domain=domain,
    )
    return {
        "case_id": case_id,
        "domain": domain,
        "features": features,
        "effect": float(outcome["effect"]),
        "outcome_causal": outcome,
        "claim_count": len(claims),
    }


def load_benchmark_training_rows(*, major_only: bool = True) -> list[TrainingSample]:
    if not BENCHMARK_PATH.exists():
        return []
    rows: list[TrainingSample] = []
    for line in BENCHMARK_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if major_only and not rec.get("labels", {}).get("is_major_event"):
            continue
        oc = rec.get("outcome_causal")
        if not oc or "effect" not in oc:
            continue
        feats = features_from_benchmark_record(rec)
        rows.append(
            TrainingSample(
                event_id=str(rec.get("event_id", "")),
                features=feats,
                effect=float(oc["effect"]),
                domain=str(rec.get("domain", "earnings")),
                source="benchmark",
            )
        )
    return rows


def build_training_samples(
    *,
    include_trace: bool = True,
    major_only: bool = True,
    case_weight: int = 5,
) -> list[TrainingSample]:
    samples: list[TrainingSample] = []
    for case in list_case_studies():
        row = load_case_training_row(case["case_id"], include_trace=include_trace)
        if row is None:
            continue
        sample = TrainingSample(
            event_id=row["case_id"],
            features=row["features"],
            effect=row["effect"],
            domain=row["domain"],
            source="case",
        )
        for _ in range(max(1, case_weight)):
            samples.append(sample)
    samples.extend(load_benchmark_training_rows(major_only=major_only))
    return samples


def train_mechanism_model(
    *,
    include_trace: bool = True,
    major_only: bool = True,
    save: bool = True,
) -> MechanismModel:
    samples = build_training_samples(include_trace=include_trace, major_only=major_only)
    if len(samples) < 5:
        raise ValueError(f"Insufficient training samples: {len(samples)}")
    model = MechanismModel().fit(samples)
    if save:
        save_model(model, default_model_path())
    return model


def calibrate_case(
    case_id: str,
    model: MechanismModel | None = None,
    *,
    include_trace: bool = True,
    write: bool = True,
) -> dict[str, Any]:
    row = load_case_training_row(case_id, include_trace=include_trace)
    if row is None:
        raise FileNotFoundError(f"Missing Phase 1/2 artifacts for case {case_id}")

    model = model or load_model(default_model_path())
    pred = model.predict(row["features"])
    posterior = calibrate_posterior(
        row["features"],
        observed_effect=row["effect"],
        domain=row["domain"],
        model_weights=pred["mechanism_weights"],
        sigma=row["outcome_causal"].get("pre_fit_rmse"),
    )

    actual_dir = "down" if row["effect"] < -0.005 else ("up" if row["effect"] > 0.005 else "neutral")
    out = {
        "case_id": case_id,
        "domain": row["domain"],
        "outcome_effect": round(row["effect"], 6),
        "outcome_method": row["outcome_causal"].get("method"),
        "predicted_effect": pred["predicted_effect"],
        "predicted_direction": pred["predicted_direction"],
        "actual_direction": actual_dir,
        "direction_match": pred["predicted_direction"] == actual_dir,
        "confidence": pred["confidence"],
        "mechanism_weights": pred["mechanism_weights"],
        "dominant_mechanism": posterior["dominant_mechanism"],
        "posterior_weights": posterior["posterior_weights"],
        "prior_weights": posterior["prior_weights"],
        "posterior_confidence": posterior["posterior_confidence"],
        "feature_vector": row["features"],
        "claim_count": row["claim_count"],
        "model_version": model.version,
        "computed_at": _utc_now(),
    }

    if write:
        out_path = CASE_ROOT / case_id / "mechanism_calibration.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path = CASE_ROOT / case_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["mechanism_calibration"] = {
            "predicted_effect": out["predicted_effect"],
            "outcome_effect": out["outcome_effect"],
            "dominant_mechanism": out["dominant_mechanism"],
            "direction_match": out["direction_match"],
            "confidence": out["confidence"],
            "artifact": "mechanism_calibration.json",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return out


def run_full_phase3(
    *,
    include_trace: bool = True,
    major_only: bool = True,
) -> dict[str, Any]:
    model = train_mechanism_model(include_trace=include_trace, major_only=major_only, save=True)

    case_rows = []
    calibrated: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for case in list_case_studies():
        case_id = case["case_id"]
        try:
            row = load_case_training_row(case_id, include_trace=False)
            if row:
                case_rows.append(row)
            calibrated[case_id] = calibrate_case(case_id, model, include_trace=include_trace, write=True)
        except Exception as exc:  # noqa: BLE001
            errors.append({"case_id": case_id, "error": str(exc)})

    holdout_cases = [
        {"case_id": r["case_id"], "features": r["features"], "effect": r["effect"], "domain": r["domain"]}
        for r in case_rows
    ]

    def _fit(train_rows: list[dict[str, Any]]) -> MechanismModel:
        samples = [
            TrainingSample(
                event_id=r["case_id"],
                features=r["features"],
                effect=r["effect"],
                domain=r["domain"],
                source="case",
            )
            for r in train_rows
        ]
        return MechanismModel().fit(samples)

    loo = leave_one_out_case_eval(holdout_cases, fit_fn=_fit) if len(holdout_cases) >= 4 else {"folds": [], "metrics": {}}
    in_sample = evaluate_predictions(
        [
            {
                "outcome_effect": v["outcome_effect"],
                "predicted_effect": v["predicted_effect"],
                "predicted_direction": v["predicted_direction"],
                "dominant_mechanism": v["dominant_mechanism"],
            }
            for v in calibrated.values()
        ]
    )

    summary = {
        "model": model.to_dict(),
        "training_samples": model.n_samples,
        "cases": len(calibrated),
        "errors": errors,
        "in_sample_metrics": in_sample,
        "leave_one_out": loo,
        "calibrated_cases": calibrated,
        "computed_at": _utc_now(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mechanism_calibration_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
