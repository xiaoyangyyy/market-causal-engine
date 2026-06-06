"""Scenario and intervention loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_causal_engine.config import KernelConfig
from worldcup_causal_engine.constants import DEFAULT_RESOURCES, default_state_with_baseline
from worldcup_causal_engine.kernel import Kernel
from worldcup_causal_engine.registry import register_all_mechanisms
from worldcup_causal_engine.reverse import analyze_result


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


PRIORS_PROFILES = {
    "v0.1": "mechanisms_v0.1.json",
    "calibrated": "mechanisms_v0.2_calibrated.json",
}


def resolve_priors_path(
    priors_path: str | Path | None = None,
    priors_profile: str | None = None,
) -> Path:
    if priors_path:
        return Path(priors_path)
    filename = PRIORS_PROFILES.get(priors_profile or "v0.1", PRIORS_PROFILES["v0.1"])
    return _project_root() / "data" / "priors" / filename


def load_priors(
    path: str | Path | None = None,
    *,
    priors_profile: str | None = None,
    scenario_id: str | None = None,
    scenario_specific: bool = False,
) -> dict[str, dict[str, float]]:
    priors_path = resolve_priors_path(path, priors_profile)
    with open(priors_path, encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    if scenario_specific and scenario_id and "_calibration_meta" in raw:
        from worldcup_causal_engine.calibration.merge_priors import priors_for_scenario

        return priors_for_scenario(raw, scenario_id)

    return {k: dict(v) for k, v in raw.items() if not k.startswith("_")}


def load_scenario(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    state = default_state_with_baseline()
    state.update(data.get("initial_state", {}))
    state.update(data.get("context", {}))

    resources = dict(DEFAULT_RESOURCES)
    resources.update(data.get("resources", {}))

    return {
        "scenario_id": data.get("scenario_id", ""),
        "initial_state": state,
        "resources": resources,
        "trigger": data.get("trigger"),
        "triggers": data.get("triggers", []),
        "context": data.get("context", {}),
        "resources_override": data.get("resources_override", {}),
    }


def load_intervention(world_id: str, base_dir: str | Path | None = None) -> list[dict[str, Any]]:
    if world_id == "W0":
        return []

    root = Path(base_dir) if base_dir else _project_root() / "data" / "interventions"
    path = root / f"{world_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Intervention file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("interventions", [])


def apply_context(kernel: Kernel, context: dict[str, float]) -> None:
    for key, value in context.items():
        if key in kernel.state:
            kernel.state[key] = float(value)


def inject_trigger(kernel: Kernel, trigger: dict[str, Any]) -> None:
    payload = dict(trigger.get("payload", {}))
    if "severity" in trigger:
        payload.setdefault("severity", trigger["severity"])
    kernel.emit(
        kind=trigger["kind"],
        payload=payload,
        at_time=int(trigger["time"]),
        priority=1,
        cause=[f"scenario_trigger:{trigger['kind']}"],
    )


def inject_interventions(kernel: Kernel, interventions: list[dict[str, Any]]) -> None:
    for item in interventions:
        kernel.do(
            kind=item["kind"],
            payload=item.get("payload", {}),
            at_time=int(item["time"]),
        )


def build_kernel(
    scenario: dict[str, Any],
    world_id: str = "W0",
    priors_path: str | Path | None = None,
    priors_profile: str | None = None,
    scenario_specific_priors: bool = False,
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
) -> Kernel:
    register_all_mechanisms()

    resources = dict(scenario["resources"])
    resources.update(scenario.get("resources_override", {}))

    priors = load_priors(
        priors_path,
        priors_profile=priors_profile,
        scenario_id=scenario.get("scenario_id"),
        scenario_specific=scenario_specific_priors,
    )
    if priors_override:
        merged = {k: dict(v) for k, v in priors.items()}
        for mech, params in priors_override.items():
            merged.setdefault(mech, {}).update(params)
        priors = merged

    kernel = Kernel(
        initial_state=scenario["initial_state"],
        resources=resources,
        priors=priors,
        config=kernel_config or KernelConfig.full(),
    )
    return kernel


def run_scenario(
    scenario_path: str | Path,
    world_id: str = "W0",
    until: int = 120,
    priors_path: str | Path | None = None,
    priors_profile: str | None = None,
    scenario_specific_priors: bool = False,
    feed_path: str | Path | None = None,
    match_id: str = "M12",
    ledger_output: str | Path | None = None,
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
    state_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    scenario = load_scenario(scenario_path)
    if state_override:
        scenario["initial_state"].update(state_override)
    config = kernel_config or KernelConfig.full()
    kernel = build_kernel(
        scenario,
        world_id,
        priors_path,
        priors_profile,
        scenario_specific_priors,
        config,
        priors_override,
    )

    if scenario.get("trigger"):
        inject_trigger(kernel, scenario["trigger"])
    for trigger in scenario.get("triggers", []):
        inject_trigger(kernel, trigger)

    if config.use_interventions:
        interventions = load_intervention(world_id)
        inject_interventions(kernel, interventions)

    ledger = None
    compiled_events: list[dict[str, Any]] = []

    if feed_path:
        from worldcup_causal_engine.feed import FeedRunner

        runner = FeedRunner(
            kernel,
            match_id=match_id,
            skip_evidence_ledger=not config.use_evidence_ledger,
        )
        runner.run_feed_file(feed_path, until=until)
        ledger = runner.ledger
        compiled_events = [e.to_dict() for e in runner._compiled_events]
    else:
        kernel.run(until=until)

    result = kernel.to_result(
        scenario_id=scenario["scenario_id"],
        world_id=world_id,
    )
    resolved = resolve_priors_path(priors_path, priors_profile)
    result["priors_path"] = str(resolved)
    result["priors_profile"] = priors_profile or ("calibrated" if resolved.name == PRIORS_PROFILES["calibrated"] else "v0.1")
    result["scenario_specific_priors"] = scenario_specific_priors
    debugger = analyze_result(result)
    result["dominant_risk_path"] = debugger.dominant_risk_path()
    result["evidence_links"] = debugger.evidence_links()

    if ledger is not None:
        result["evidence_ledger"] = ledger.summary()
        result["compiled_events"] = compiled_events
        if ledger_output:
            out = Path(ledger_output)
            out.parent.mkdir(parents=True, exist_ok=True)
            ledger.save(out)
            result["ledger_path"] = str(out)

    return result


def run_proposal_demo(
    scenario_path: str | Path,
    *,
    proposal_kind: str = "official_clarification",
    proposal_time: int = 87,
    proposal_payload: dict[str, Any] | None = None,
    until: int = 120,
) -> dict[str, Any]:
    """Phase 5 demo: LLM proposer submits intervention; kernel verifies before run."""
    from worldcup_causal_engine.proposers.llm import LLMProposer

    scenario = load_scenario(scenario_path)
    kernel = build_kernel(scenario, world_id="W0")

    for trigger in scenario.get("triggers", []):
        inject_trigger(kernel, trigger)
    if scenario.get("trigger"):
        inject_trigger(kernel, scenario["trigger"])

    kernel.run(until=max(0, proposal_time - 1))

    proposer = LLMProposer(proposer_id="llm-demo")
    vr = proposer.propose_kind(
        kernel,
        proposal_kind,
        time=proposal_time,
        payload=proposal_payload or {"topic": "controversial_call", "credibility": 0.7},
    )

    kernel.run(until=until)
    result = kernel.to_result(
        scenario_id=scenario["scenario_id"],
        world_id="proposal_demo",
    )
    result["proposal_verification"] = vr.to_dict()
    return result


def run_llm_propose_demo(
    scenario_path: str | Path,
    *,
    until: int = 120,
    use_api: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    mock_kind: str | None = None,
    mock_time: int = 87,
    max_attempts: int = 3,
    skip_context: bool = False,
) -> dict[str, Any]:
    """LLM proposes intervention via API (or mock); kernel verifies with retries."""
    from worldcup_causal_engine.proposers.context import (
        gather_intervention_context,
        proposal_checkpoint,
    )
    from worldcup_causal_engine.proposers.llm import LLMProposer

    scenario = load_scenario(scenario_path)
    kernel = build_kernel(scenario, world_id="W0")

    for trigger in scenario.get("triggers", []):
        inject_trigger(kernel, trigger)
    if scenario.get("trigger"):
        inject_trigger(kernel, scenario["trigger"])

    checkpoint = proposal_checkpoint(scenario)
    kernel.run(until=checkpoint)

    context = (
        {"checkpoint_minute": checkpoint, "baseline_w0": {}, "best_cut_points": []}
        if skip_context
        else gather_intervention_context(scenario_path, until=until)
    )
    context["checkpoint_minute"] = checkpoint
    baseline_risk = context.get("baseline_w0", {}).get("final_risk", {})

    proposer = LLMProposer(proposer_id="llm-api")
    proposal, vr, raw, attempts = proposer.propose_via_api(
        kernel,
        scenario,
        use_api=use_api,
        context=context,
        max_attempts=max_attempts,
        mock_kind=mock_kind,
        mock_time=mock_time,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    kernel.run(until=until)
    result = kernel.to_result(
        scenario_id=scenario["scenario_id"],
        world_id="llm_propose_demo",
    )
    result["llm_proposal"] = proposal.to_dict()
    result["proposal_verification"] = vr.to_dict()
    result["llm_raw"] = raw
    result["proposal_attempts"] = attempts
    result["intervention_context"] = {
        "checkpoint_minute": checkpoint,
        "recommended_interventions": context.get("recommended_interventions", []),
        "best_cut_points": context.get("best_cut_points", []),
        "scenario_hints": context.get("scenario_hints", []),
    }
    final_risk = result.get("final_risk", {})
    result["intervention_effect"] = {
        "baseline_final_risk": baseline_risk,
        "actual_final_risk": final_risk,
        "accepted": vr.accepted,
        "improved": (
            vr.accepted
            and (
                final_risk.get("verbal_conflict", 1.0)
                < baseline_risk.get("verbal_conflict", 1.0)
                or final_risk.get("panic", 1.0) < baseline_risk.get("panic", 1.0)
            )
        ),
    }
    return result
