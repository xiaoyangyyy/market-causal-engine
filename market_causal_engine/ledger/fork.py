"""Trace fork and counterfactual replay without full scenario re-run from t=0."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from market_causal_engine.ledger.log import CausalLedger
from market_causal_engine.ledger.snapshot import CausalSnapshot


@dataclass
class ForkSpec:
    """Fork counterfactual branch from a baseline ledger."""

    parent_ledger_id: str
    fork_before_kind: str
    fork_before_event_id: str | None = None
    interventions: list[dict[str, Any]] = field(default_factory=list)
    branch_id: str = "fork_W1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_ledger_id": self.parent_ledger_id,
            "fork_before_kind": self.fork_before_kind,
            "fork_before_event_id": self.fork_before_event_id,
            "interventions": self.interventions,
            "branch_id": self.branch_id,
        }


@dataclass
class ForkResult:
    branch_id: str
    fork_point: str | None
    snapshot_id: str | None
    final_risk: dict[str, float]
    dominant_path: list[str]
    ledger: CausalLedger
    equivalence_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "fork_point": self.fork_point,
            "snapshot_id": self.snapshot_id,
            "final_risk": self.final_risk,
            "dominant_path": self.dominant_path,
            "equivalence_note": self.equivalence_note,
            "ledger": self.ledger.to_dict(),
        }


def fork_at(
    baseline_ledger: CausalLedger,
    fork_before_kind: str,
    fork_before_event_id: str | None = None,
) -> tuple[CausalSnapshot | None, ForkSpec]:
    """Locate snapshot from last executed event before target kind."""
    snap = None
    if fork_before_event_id:
        snap = baseline_ledger.get_snapshot(fork_before_event_id)

    if snap is None:
        prev_event_id: str | None = None
        for entry in baseline_ledger.entries:
            if entry.action == "executed":
                if entry.kind == fork_before_kind:
                    break
                prev_event_id = entry.event_id
        if prev_event_id:
            snap = baseline_ledger.get_snapshot(prev_event_id)

    spec = ForkSpec(
        parent_ledger_id=baseline_ledger.ledger_id,
        fork_before_kind=fork_before_kind,
        fork_before_event_id=snap.event_id if snap else fork_before_event_id,
    )
    return snap, spec


def _restore_kernel_from_snapshot(
    snapshot: CausalSnapshot,
    priors: dict | None = None,
    *,
    ledger_id: str = "fork_branch",
):
    from market_causal_engine.config import KernelConfig
    from market_causal_engine.kernel import Event, Kernel

    k = Kernel(
        initial_state=copy.deepcopy(snapshot.state),
        resources=copy.deepcopy(snapshot.resources),
        priors=priors or {},
        config=KernelConfig.full(),
    )
    k.flags = set(snapshot.flags)
    k._executed_kinds = list(snapshot.executed_kinds)
    k._current_time = snapshot.time
    if k.ledger is not None:
        k.ledger.ledger_id = ledger_id

    for item in snapshot.pending_events:
        event = Event(
            id=item.get("id", k._next_event_id()),
            kind=item["kind"],
            time=int(item["time"]),
            priority=int(item.get("priority", 5)),
            payload=dict(item.get("payload", {})),
            cause=list(item.get("cause", [])),
            seq=int(item.get("seq", 0)),
        )
        k._events[event.id] = event
        k._enqueue(event)

    return k


def replay_fork(
    baseline_ledger: CausalLedger,
    fork_before_kind: str,
    interventions: list[dict[str, Any]],
    until: int = 120,
    priors: dict | None = None,
    branch_id: str = "fork_branch",
) -> ForkResult:
    """Restore snapshot before fork point, inject interventions, continue simulation."""
    from market_causal_engine.registry import register_all_mechanisms

    register_all_mechanisms()
    snap, spec = fork_at(baseline_ledger, fork_before_kind)
    spec.interventions = interventions
    spec.branch_id = branch_id

    if snap is None:
        return ForkResult(
            branch_id=branch_id,
            fork_point=None,
            snapshot_id=None,
            final_risk={},
            dominant_path=[],
            ledger=CausalLedger(ledger_id=branch_id),
            equivalence_note="fork_failed:no_snapshot",
        )

    kernel = _restore_kernel_from_snapshot(snap, priors, ledger_id=branch_id)

    for item in interventions:
        kernel.do(
            kind=item["kind"],
            payload=item.get("payload", {}),
            at_time=int(item["time"]),
        )

    kernel.run(until=until)
    result = kernel.to_result(world_id=branch_id)

    return ForkResult(
        branch_id=branch_id,
        fork_point=fork_before_kind,
        snapshot_id=snap.snapshot_id,
        final_risk=result.get("final_risk", {}),
        dominant_path=result.get("dominant_path", []),
        ledger=kernel.ledger or CausalLedger(ledger_id=branch_id),
        equivalence_note="fork_replay_complete",
    )


def replay_fork_from_scenario(
    scenario_path: str | Path,
    baseline_world: str,
    fork_before_kind: str,
    intervention_world: str,
    until: int = 120,
) -> tuple[dict[str, Any], ForkResult, dict[str, Any]]:
    """Compare full intervention run vs fork-replay intervention."""
    from market_causal_engine.scenarios import load_intervention, run_scenario

    baseline = run_scenario(scenario_path, world_id=baseline_world, until=until)
    full_intervention = run_scenario(scenario_path, world_id=intervention_world, until=until)

    ledger_data = baseline.get("causal_ledger")
    if ledger_data:
        ledger = CausalLedger.from_dict(ledger_data)
    else:
        ledger = CausalLedger.from_trace(
            baseline.get("trace", []), ledger_id=f"baseline_{baseline_world}"
        )

    interventions = load_intervention(intervention_world)
    fork_result = replay_fork(
        baseline_ledger=ledger,
        fork_before_kind=fork_before_kind,
        interventions=interventions,
        until=until,
        branch_id=f"fork_{intervention_world}",
    )

    return baseline, fork_result, full_intervention


def diff_branches(path_a: list[str], path_b: list[str]) -> dict[str, Any]:
    shared = 0
    for a, b in zip(path_a, path_b):
        if a == b:
            shared += 1
        else:
            break
    return {
        "fork_point": path_a[shared - 1] if shared > 0 else None,
        "path_a": path_a,
        "path_b": path_b,
        "only_a": path_a[shared:],
        "only_b": path_b[shared:],
        "diverged": path_a != path_b,
    }
