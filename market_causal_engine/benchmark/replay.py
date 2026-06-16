"""Replay benchmark events through case study or scenario engines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.calibration import attach_calibration
from market_causal_engine.config import KernelConfig
from market_causal_engine.constants import SCENARIO_FILES
from market_causal_engine.scenarios import load_scenario, run_scenario


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _scenario_path(scenario_id: str) -> Path:
    filename = SCENARIO_FILES.get(scenario_id)
    if not filename:
        raise ValueError(f"Unknown scenario_id: {scenario_id}")
    return _project_root() / "data" / "market" / "scenarios" / filename


def infer_simulated_direction(result: dict[str, Any], *, event: dict[str, Any] | None = None) -> str:
    try:
        from market_causal_engine.learned.direction import infer_direction

        return infer_direction(result, event=event)
    except Exception:  # noqa: BLE001
        risk = result.get("final_risk", {})
        pressure = float(risk.get("directional_pressure", 0.0))
        if pressure < -0.05:
            return "up"
        if pressure > 0.12:
            return "down"
        return "neutral"


def replay_case_study_event(
    event: BenchmarkEvent,
    *,
    until: int = 120,
    world_id: str = "W0",
    atom_filter: str | None = None,
) -> dict[str, Any]:
    from market_causal_engine.case_study import run_case_study

    case_id = event.case_id or event.event_id
    if atom_filter:
        return _replay_case_with_atom_filter(case_id, until=until, world_id=world_id, atom_filter=atom_filter)
    result = run_case_study(case_id, as_of=until, world_id=world_id)
    result["benchmark_event_id"] = event.event_id
    result["replay_mode"] = "case_study"
    return result


def _replay_case_with_atom_filter(
    case_id: str,
    *,
    until: int,
    world_id: str,
    atom_filter: str,
) -> dict[str, Any]:
    from market_causal_engine.analysis import enrich_result
    from market_causal_engine.calibration import attach_calibration
    from market_causal_engine.case_study import build_case_report, load_case_manifest
    from market_causal_engine.config import KernelConfig
    from market_causal_engine.evidence import load_atoms
    from market_causal_engine.feed import FeedRunner
    from market_causal_engine.lookahead import LookAheadPolicy, filter_admissible_atoms
    from market_causal_engine.reverse import analyze_result, infer_market_regime
    from market_causal_engine.scenarios import build_kernel, inject_interventions, load_intervention, load_scenario

    manifest = load_case_manifest(case_id)
    root = Path(manifest["_root"])
    policy = LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    all_atoms = load_atoms(root / manifest.get("atoms_path", "atoms.jsonl"))
    all_atoms = filter_atoms_by_channel(all_atoms, atom_filter)
    admissible, lookahead_report = filter_admissible_atoms(all_atoms, as_of=until, policy=policy)

    scenario = load_scenario(root / manifest.get("scenario_path", "scenario.json"))
    domain = str(manifest.get("domain", "earnings"))
    config = KernelConfig.full()
    kernel = build_kernel(scenario, world_id, domain=domain)
    if config.use_interventions:
        inject_interventions(kernel, load_intervention(world_id, case_root=root))

    runner = FeedRunner(
        kernel,
        ticker=manifest.get("ticker", "UNKNOWN"),
        skip_evidence_ledger=not config.use_evidence_ledger,
        lookahead_policy=policy,
        as_of=until,
        domain=domain,
    )
    runner.run_atoms(admissible, until=until)

    result = kernel.to_result(scenario_id=scenario.get("scenario_id", case_id), world_id=world_id)
    debugger = analyze_result(result)
    result["dominant_causal_path"] = debugger.dominant_causal_path()
    result["dominant_risk_path"] = result["dominant_causal_path"]
    enrich_result(result)
    result["lookahead_audit"] = lookahead_report.to_dict()
    result["case_study"] = build_case_report(manifest, result, until, runner)
    attach_calibration(result, manifest.get("observed_outcomes", {}))
    result["domain"] = domain
    result["benchmark_event_id"] = case_id
    result["replay_mode"] = f"case_study:{atom_filter}"
    result["ablation"] = atom_filter
    from market_causal_engine.platform.pit_hardening import attach_pit_audit

    attach_pit_audit(result, manifest=manifest, atoms=all_atoms, as_of_minutes=until, policy=policy)
    return result


def filter_atoms_by_channel(atoms: list, channel: str) -> list:
    """Channel ablation filters for case-study feed replay."""
    if channel == "full":
        return atoms

    filtered = []
    for atom in atoms:
        src = (atom.source or "").lower()
        tags = set(atom.tags or [])
        source_class = str(atom.metadata.get("source_class", "")).lower()
        extracted_by = str(atom.metadata.get("extracted_by", "")).lower()

        if channel == "no_news":
            if source_class == "news_wire":
                continue
            if "news" in src or "market_watch" in src:
                continue
        elif channel == "no_sec":
            if source_class == "primary_filing":
                continue
            if src in {"8-k", "sec", "earnings_call_transcript", "guidance"}:
                continue
            if "filing" in extracted_by or extracted_by in {"earnings_release", "guidance_cut", "transcript_quote"}:
                continue
        elif channel == "no_price":
            if tags & {"intraday", "options", "volume"}:
                continue
            if extracted_by in {"market_move", "options_vol", "intraday_vol"}:
                continue
        filtered.append(atom)
    return filtered


def replay_scenario_event(
    event: BenchmarkEvent,
    *,
    until: int = 120,
    world_id: str = "W0",
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    from market_causal_engine.constants import SCENARIO_DOMAIN

    from market_causal_engine.scenarios import (
        event_replay_severity_scale,
        load_scenario,
        scale_scenario_triggers,
    )

    scenario_id = event.scenario_id or "E1"
    domain = str(event.domain or SCENARIO_DOMAIN.get(scenario_id, "earnings"))
    path = _scenario_path(scenario_id)
    scenario = load_scenario(path)
    severity_scale = event_replay_severity_scale(event)
    if severity_scale < 0.999:
        scenario = scale_scenario_triggers(scenario, severity_scale)
    result = run_scenario(
        path,
        world_id=world_id,
        until=until,
        ticker=event.ticker or "ACME",
        kernel_config=kernel_config,
        priors_override=priors_override,
        domain=domain,
        scenario=scenario,
    )
    result["replay_severity_scale"] = severity_scale
    attach_calibration(result, event.observed_outcomes)
    result["_benchmark_event"] = event.to_dict()
    result["domain"] = domain
    result["benchmark_event_id"] = event.event_id
    result["replay_mode"] = "scenario"
    result["simulated_direction"] = infer_simulated_direction(result, event=event.to_dict())
    result["observed_direction"] = event.observed_outcomes.get("direction")
    return result


def replay_placebo_event(
    event: BenchmarkEvent,
    *,
    until: int = 30,
) -> dict[str, Any]:
    """Run baseline kernel with no scenario triggers — detect spurious activation."""
    from market_causal_engine.analysis import enrich_result
    from market_causal_engine.reverse import analyze_result, infer_market_regime
    from market_causal_engine.scenarios import build_kernel

    scenario = load_scenario(_scenario_path(event.scenario_id or "E1"))
    # Strip triggers for placebo control
    scenario = {
        **scenario,
        "trigger": None,
        "triggers": [],
        "initial_state": {
            **scenario["initial_state"],
            "fundamental_expectation": 0.5,
            "investor_sentiment": 0.5,
        },
    }
    from market_causal_engine.constants import SCENARIO_DOMAIN

    domain = str(event.domain or SCENARIO_DOMAIN.get(event.scenario_id or "E1", "earnings"))
    kernel = build_kernel(scenario, "W0", domain=domain)
    kernel.run(until=until)
    result = kernel.to_result(scenario_id=f"placebo_{event.event_id}", world_id="W0")
    debugger = analyze_result(result)
    result["dominant_causal_path"] = debugger.dominant_causal_path()
    enrich_result(result)
    result["market_regime"] = infer_market_regime(result["final_state"])
    result["benchmark_event_id"] = event.event_id
    result["domain"] = domain
    result["replay_mode"] = "placebo"
    result["simulated_direction"] = infer_simulated_direction(result, event=event.to_dict())
    result["observed_direction"] = "neutral"
    return result


def replay_event(
    event: BenchmarkEvent,
    *,
    until: int = 120,
    atom_filter: str | None = None,
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
    prefer_catalog_feed: bool = True,
    attach_outcome: bool = True,
    car_ablation: bool | None = None,
) -> dict[str, Any]:
    if event.replay_mode == "case_study" or (event.case_id and event.replay_mode != "scenario"):
        result = replay_case_study_event(event, until=until, atom_filter=atom_filter)
    elif event.replay_mode == "placebo":
        result = replay_placebo_event(event, until=min(until, 30))
    elif prefer_catalog_feed and event.corpus == "earnings_sp500_2016_2025":
        from market_causal_engine.benchmark.catalog.claims import has_effective_catalog_claims
        from market_causal_engine.benchmark.catalog.replay import (
            has_catalog_atoms,
            replay_catalog_feed_event,
        )
        from market_causal_engine.benchmark.catalog.router import (
            attach_predicted_effect,
            build_router_features,
        )
        from market_causal_engine.learned.store import load_learned_store

        if has_catalog_atoms(event.event_id) and has_effective_catalog_claims(event.event_id):
            ev_dict = event.to_dict()
            catalog_result = replay_catalog_feed_event(event, until=until, atom_filter=atom_filter)
            store = load_learned_store()
            catalog_model = store.get("catalog_domain_model")
            router = store.get("catalog_router")
            if router and router.coefficients:
                scenario_result = replay_scenario_event(
                    event,
                    until=until,
                    kernel_config=kernel_config,
                    priors_override=priors_override,
                )
                if catalog_model is not None:
                    attach_predicted_effect(catalog_result, ev_dict, catalog_model)
                    attach_predicted_effect(scenario_result, ev_dict, catalog_model)
                feats = build_router_features(catalog_result, scenario_result, event=ev_dict)
                if router.prefer_catalog(feats):
                    result = catalog_result
                else:
                    scenario_result["catalog_fallback"] = True
                    scenario_result["router_preferred"] = "scenario"
                    result = scenario_result
            else:
                scenario_result = replay_scenario_event(
                    event,
                    until=until,
                    kernel_config=kernel_config,
                    priors_override=priors_override,
                )
                scenario_result["catalog_fallback"] = True
                scenario_result["router_preferred"] = "scenario"
                result = scenario_result
        else:
            result = replay_scenario_event(
                event,
                until=until,
                kernel_config=kernel_config,
                priors_override=priors_override,
            )
    else:
        result = replay_scenario_event(
            event,
            until=until,
            kernel_config=kernel_config,
            priors_override=priors_override,
        )

    result["_benchmark_event"] = event.to_dict()
    if attach_outcome:
        from market_causal_engine.counterfactuals.outcome_layer import attach_outcome_causal

        attach_outcome_causal(
            result,
            event,
            run_placebo=False,
            car_ablation=car_ablation,
            until=until,
        )
    return result
