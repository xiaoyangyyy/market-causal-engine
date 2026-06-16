"""Historical case study loader and feed-only replay runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.analysis import enrich_result
from market_causal_engine.config import KernelConfig
from market_causal_engine.evidence import load_atoms
from market_causal_engine.feed import FeedRunner
from market_causal_engine.lookahead import LookAheadPolicy, filter_admissible_atoms
from market_causal_engine.reverse import analyze_result, infer_market_regime
from market_causal_engine.scenarios import (
    build_kernel,
    inject_interventions,
    load_intervention,
    load_scenario,
)


def _case_studies_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "market" / "case_studies"


def list_case_studies() -> list[dict[str, Any]]:
    root = _case_studies_root()
    cases: list[dict[str, Any]] = []
    if not root.exists():
        return cases
    for manifest_path in sorted(root.glob("*/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases.append(
            {
                "case_id": data.get("case_id", manifest_path.parent.name),
                "ticker": data.get("ticker"),
                "event_date": data.get("event_date"),
                "event_type": data.get("event_type"),
                "domain": data.get("domain", data.get("mvp", "earnings")),
                "description": data.get("description", ""),
            }
        )
    return cases


def load_case_manifest(case_id: str) -> dict[str, Any]:
    path = _case_studies_root() / case_id / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Case study not found: {case_id} ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_root"] = str(path.parent)
    return data


def _attach_mechanism_calibration(result: dict[str, Any], case_root: Path) -> None:
    cal_path = case_root / "mechanism_calibration.json"
    if not cal_path.exists():
        return
    result["mechanism_calibration"] = json.loads(cal_path.read_text(encoding="utf-8"))
    if isinstance(result.get("case_study"), dict):
        result["case_study"]["mechanism_calibration"] = result["mechanism_calibration"]


def run_case_study(
    case_id: str,
    *,
    world_id: str = "W0",
    until: int | None = None,
    as_of: int | None = None,
    strict_lookahead: bool | None = None,
    validate_only: bool = False,
    priors_path: str | Path | None = None,
    ledger_output: str | Path | None = None,
) -> dict[str, Any]:
    manifest = load_case_manifest(case_id)
    root = Path(manifest["_root"])
    horizon = as_of if as_of is not None else until or int(manifest.get("default_until", 180))

    policy = LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    if strict_lookahead is not None:
        policy = LookAheadPolicy(
            strict=strict_lookahead,
            forbid_post_hoc_sources=policy.forbid_post_hoc_sources,
            forbidden_source_classes=policy.forbidden_source_classes,
            max_published_skew=policy.max_published_skew,
        )

    atoms_path = root / manifest.get("atoms_path", "atoms.jsonl")
    all_atoms = load_atoms(atoms_path)
    admissible, lookahead_report = filter_admissible_atoms(
        all_atoms, as_of=horizon, policy=policy
    )

    if validate_only:
        from market_causal_engine.platform.pit_hardening import attach_pit_audit

        pit_only: dict[str, Any] = {
            "case_id": case_id,
            "as_of": horizon,
            "lookahead_audit": lookahead_report.to_dict(),
            "atom_count_total": len(all_atoms),
            "atom_count_admissible": len(admissible),
        }
        attach_pit_audit(pit_only, manifest=manifest, atoms=all_atoms, as_of_minutes=horizon, policy=policy)
        return pit_only

    scenario_path = root / manifest.get("scenario_path", "scenario.json")
    scenario = load_scenario(scenario_path)
    domain = str(manifest.get("domain", "earnings"))
    config = KernelConfig.full()
    kernel = build_kernel(scenario, world_id, priors_path, domain=domain)

    if config.use_interventions:
        inject_interventions(
            kernel,
            load_intervention(world_id, case_root=root),
        )

    runner = FeedRunner(
        kernel,
        ticker=manifest.get("ticker", "UNKNOWN"),
        skip_evidence_ledger=not config.use_evidence_ledger,
        lookahead_policy=policy,
        as_of=horizon,
        domain=domain,
    )
    runner.run_atoms(admissible, until=horizon)

    result = kernel.to_result(
        scenario_id=scenario.get("scenario_id", case_id),
        world_id=world_id,
    )
    debugger = analyze_result(result)
    result["dominant_causal_path"] = debugger.dominant_causal_path()
    result["dominant_risk_path"] = result["dominant_causal_path"]
    result["evidence_links"] = debugger.evidence_links()
    result["market_regime"] = infer_market_regime(result["final_state"])
    enrich_result(result)

    result["compiled_events"] = [e.to_dict() for e in runner._compiled_events]
    result["lookahead_audit"] = lookahead_report.to_dict()
    from market_causal_engine.platform.pit_hardening import attach_pit_audit

    attach_pit_audit(result, manifest=manifest, atoms=all_atoms, as_of_minutes=horizon, policy=policy)
    result["case_study"] = build_case_report(manifest, result, horizon, runner)
    from market_causal_engine.calibration import attach_calibration

    attach_calibration(result, manifest.get("observed_outcomes", {}))
    result["domain"] = domain
    _attach_mechanism_calibration(result, root)

    if runner.ledger is not None:
        result["evidence_ledger"] = (
            runner.ledger.summary() if hasattr(runner.ledger, "summary") else runner.ledger.to_dict()
        )
        if ledger_output:
            out = Path(ledger_output)
            out.parent.mkdir(parents=True, exist_ok=True)
            runner.ledger.save(out)
            result["ledger_path"] = str(out)

    return result


def build_case_report(
    manifest: dict[str, Any],
    result: dict[str, Any],
    horizon: int,
    runner: FeedRunner,
) -> dict[str, Any]:
    observed = manifest.get("observed_outcomes", {})
    sim_risk = result.get("final_risk", {})
    forensic = result.get("forensic_output", result.get("mvp_output", {}))
    calibrated = result.get("calibrated_impact", {})

    from market_causal_engine.benchmark.replay import infer_simulated_direction

    sim_direction = infer_simulated_direction(result)
    obs_direction = observed.get("direction", "unknown")
    direction_match = sim_direction == obs_direction if obs_direction != "unknown" else None

    report = {
        "case_id": manifest.get("case_id"),
        "ticker": manifest.get("ticker"),
        "event_date": manifest.get("event_date"),
        "event_type": manifest.get("event_type"),
        "domain": manifest.get("domain", manifest.get("mvp", "earnings")),
        "time_axis": manifest.get("time_axis", {}),
        "as_of_minutes": horizon,
        "feed_only": True,
        "atoms_ingested": len(runner._compiled_events),
        "atoms_rejected_lookahead": result.get("lookahead_audit", {}).get("rejected_count", 0),
        "pit_audit_passed": (result.get("pit_audit") or {}).get("passed"),
        "pit_envelope_coverage": (result.get("pit_audit") or {}).get("envelope_coverage"),
        "direction_match": direction_match,
        "observed_outcomes": observed,
        "simulated_outcomes": {
            "direction": sim_direction,
            "directional_pressure": sim_risk.get("directional_pressure"),
            "drawdown_risk": sim_risk.get("drawdown_risk"),
            "volatility_risk": sim_risk.get("volatility_risk"),
            "liquidity_stress": sim_risk.get("liquidity_stress"),
        },
        "calibrated_impact": calibrated,
        "qualitative_alignment": {
            "direction_match": direction_match,
            "dominant_narrative_observed": observed.get("dominant_narrative"),
            "dominant_path_simulated": result.get("dominant_causal_path", []),
            "dominant_move_reason": forensic.get("dominant_move_reason") or forensic.get("interpretation"),
            "estimated_vs_observed_ah": {
                "estimated_pct": calibrated.get("estimated_after_hours_return_pct"),
                "observed_pct": observed.get("after_hours_return_pct"),
                "error_pct": calibrated.get("after_hours_error_pct"),
                "within_band": calibrated.get("after_hours_within_band"),
            },
        },
        "methodology_note": (
            "Observed returns are post-hoc calibration labels only; "
            "they are NOT fed into the kernel (look-ahead safe)."
        ),
    }
    if manifest.get("outcome_causal"):
        report["outcome_causal"] = manifest["outcome_causal"]
    if manifest.get("causal_claims"):
        report["causal_claims"] = manifest["causal_claims"]
    if manifest.get("mechanism_calibration"):
        report["mechanism_calibration"] = manifest["mechanism_calibration"]
    return report


def run_case_counterfactual(
    case_id: str,
    worlds: list[str] | None = None,
    until: int | None = None,
) -> dict[str, Any]:
    from market_causal_engine.reverse import diff_results

    worlds = worlds or ["W0", "W1", "W3", "W6"]
    horizon = until or load_case_manifest(case_id).get("default_until", 180)
    runs = {wid: run_case_study(case_id, world_id=wid, until=horizon) for wid in worlds}
    baseline = runs["W0"]
    diffs = {
        wid: diff_results(baseline, run)
        for wid, run in runs.items()
        if wid != "W0"
    }
    return {
        "case_id": case_id,
        "as_of": horizon,
        "runs": {wid: r.get("case_study", {}) for wid, r in runs.items()},
        "counterfactual_diffs": diffs,
    }
