"""Scenario and intervention loading for market causal engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.config import KernelConfig
from market_causal_engine.constants import DEFAULT_RESOURCES, default_state_with_baseline
from market_causal_engine.kernel import Kernel
from market_causal_engine.registry import register_all_mechanisms
from market_causal_engine.reverse import analyze_result, infer_market_regime
from market_causal_engine.analysis import enrich_result


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


PRIORS_PROFILES = {
    "v0.1": "mechanisms_v0.1.json",
}


def resolve_priors_path(
    priors_path: str | Path | None = None,
    priors_profile: str | None = None,
) -> Path:
    if priors_path:
        return Path(priors_path)
    filename = PRIORS_PROFILES.get(priors_profile or "v0.1", PRIORS_PROFILES["v0.1"])
    return _project_root() / "data" / "market" / "priors" / filename


def load_priors(
    path: str | Path | None = None,
    *,
    priors_profile: str | None = None,
) -> dict[str, dict[str, float]]:
    priors_path = resolve_priors_path(path, priors_profile)
    with open(priors_path, encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)
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
        "description": data.get("description", ""),
    }


def load_intervention(
    world_id: str,
    base_dir: str | Path | None = None,
    *,
    case_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    if world_id == "W0":
        return []

    if case_root is not None:
        case_path = Path(case_root) / "interventions" / f"{world_id}.json"
        if case_path.exists():
            with open(case_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("interventions", [])

    root = Path(base_dir) if base_dir else _project_root() / "data" / "market" / "interventions"
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
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
) -> Kernel:
    register_all_mechanisms()

    resources = dict(scenario["resources"])
    resources.update(scenario.get("resources_override", {}))

    priors = load_priors(priors_path, priors_profile=priors_profile)
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
    until: int = 30,
    priors_path: str | Path | None = None,
    priors_profile: str | None = None,
    feed_path: str | Path | None = None,
    ticker: str = "ACME",
    ledger_output: str | Path | None = None,
    kernel_config: KernelConfig | None = None,
    priors_override: dict[str, dict[str, float]] | None = None,
    state_override: dict[str, float] | None = None,
    case_root: str | Path | None = None,
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
        config,
        priors_override,
    )

    if scenario.get("trigger"):
        inject_trigger(kernel, scenario["trigger"])
    for trigger in scenario.get("triggers", []):
        inject_trigger(kernel, trigger)

    if config.use_interventions:
        interventions = load_intervention(world_id, case_root=case_root)
        inject_interventions(kernel, interventions)

    ledger = None
    compiled_events: list[dict[str, Any]] = []

    if feed_path:
        from market_causal_engine.feed import FeedRunner

        runner = FeedRunner(
            kernel,
            ticker=ticker,
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
    result["priors_profile"] = priors_profile or "v0.1"
    debugger = analyze_result(result)
    result["dominant_causal_path"] = debugger.dominant_causal_path()
    result["dominant_risk_path"] = result["dominant_causal_path"]
    result["evidence_links"] = debugger.evidence_links()
    result["market_regime"] = infer_market_regime(result["final_state"])
    enrich_result(result)

    if ledger is not None:
        result["evidence_ledger"] = (
            ledger.summary() if hasattr(ledger, "summary") else ledger.to_dict()
        )
        result["compiled_events"] = compiled_events
        if ledger_output:
            out = Path(ledger_output)
            out.parent.mkdir(parents=True, exist_ok=True)
            ledger.save(out)
            result["ledger_path"] = str(out)

    return result


def run_counterfactual_suite(
    scenario_path: str | Path,
    worlds: list[str] | None = None,
    until: int = 30,
) -> dict[str, Any]:
    """Run baseline + counterfactual worlds and compute impact diffs."""
    from market_causal_engine.constants import WORLD_IDS

    worlds = worlds or WORLD_IDS
    runs: dict[str, dict[str, Any]] = {}
    for wid in worlds:
        runs[wid] = run_scenario(scenario_path, world_id=wid, until=until)

    baseline = runs.get("W0", runs[worlds[0]])
    diffs: dict[str, Any] = {}
    for wid, run in runs.items():
        if wid == "W0":
            continue
        from market_causal_engine.reverse import diff_results

        diffs[wid] = diff_results(baseline, run)

    return {
        "scenario_id": baseline.get("scenario_id"),
        "runs": runs,
        "counterfactual_diffs": diffs,
        "baseline_drawdown": baseline.get("final_risk", {}).get("drawdown_risk"),
    }
