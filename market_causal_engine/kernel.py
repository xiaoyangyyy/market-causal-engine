"""Runtime causal kernel: scheduling, state, flags, resources, trace."""

from __future__ import annotations

import copy
import heapq
from dataclasses import dataclass, field, replace
from typing import Any

from market_causal_engine.config import KernelConfig
from market_causal_engine.constants import (
    OUTCOME_DISPLAY,
    OUTCOME_KEYS,
    STATE_KEYS,
    default_state_with_baseline,
)
from market_causal_engine.ir.proposal import Proposal, VerificationResult
from market_causal_engine.registry import get_handler, get_spec


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _accumulate_outcome(old: float, delta: float) -> float:
    """Diminishing returns on outcome scores to avoid saturation from stacked events."""
    if delta >= 0:
        return _clamp(old + delta * (1.0 - old))
    return _clamp(old + delta * max(old, 0.05))


@dataclass
class Event:
    id: str
    kind: str
    time: int
    priority: int = 5
    payload: dict[str, Any] = field(default_factory=dict)
    cause: list[str] = field(default_factory=list)
    status: str = "pending"
    seq: int = 0


@dataclass
class TraceEntry:
    event_id: str
    kind: str
    time: int
    action: str
    patch: dict[str, float] = field(default_factory=dict)
    flags_delta: dict[str, str] = field(default_factory=dict)
    resource_delta: dict[str, float] = field(default_factory=dict)
    cause: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    proposal_id: str | None = None
    verification: dict[str, Any] | None = None
    proposer: str | None = None
    ledger_entry_id: str | None = None


class Kernel:
    def __init__(
        self,
        initial_state: dict[str, float] | None = None,
        resources: dict[str, float] | None = None,
        priors: dict[str, dict[str, float]] | None = None,
        config: KernelConfig | None = None,
    ):
        self.config = config or KernelConfig.full()
        base = default_state_with_baseline()
        if initial_state:
            base.update(initial_state)
        self.state: dict[str, float] = base
        self.resources: dict[str, float] = dict(resources or {})
        self.flags: set[str] = set()
        self.trace: list[TraceEntry] = []
        self.priors: dict[str, dict[str, float]] = priors or {}
        self._queue: list[tuple[int, int, int, Event]] = []
        self._event_counter = 0
        self._seq = 0
        self._current_time = 0
        self._executed_kinds: list[str] = []
        self._events: dict[str, Event] = {}
        self._proposal_counter = 0
        self.ledger = None
        if self.config.use_causal_ledger:
            from market_causal_engine.ledger.log import CausalLedger

            self.ledger = CausalLedger(ledger_id="main")

    def _next_event_id(self) -> str:
        self._event_counter += 1
        return f"E{self._event_counter}"

    def _enqueue(self, event: Event) -> None:
        priority = event.priority if self.config.use_priority else 5
        heapq.heappush(self._queue, (event.time, priority, event.seq, event))

    def _record_trace(self, entry: TraceEntry) -> None:
        if self.config.use_trace:
            self.trace.append(entry)
        if self.ledger is not None:
            ledger_entry = self.ledger.append(
                event_id=entry.event_id,
                kind=entry.kind,
                time=entry.time,
                action=entry.action,
                cause=entry.cause,
                patch=entry.patch,
                flags_delta=entry.flags_delta,
                resource_delta=entry.resource_delta,
                blocked_reason=entry.blocked_reason,
                proposal_id=entry.proposal_id,
                verification=entry.verification,
                proposer=entry.proposer,
            )
            entry.ledger_entry_id = ledger_entry.entry_id

    def _pending_event_dicts(self) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for event_time, priority, seq, event in sorted(self._queue):
            pending.append(
                {
                    "id": event.id,
                    "kind": event.kind,
                    "time": event_time,
                    "priority": priority,
                    "seq": seq,
                    "payload": dict(event.payload),
                    "cause": list(event.cause),
                }
            )
        return pending

    def _save_snapshot(self, event: Event) -> None:
        if self.ledger is None:
            return
        self.ledger.save_snapshot(
            event_id=event.id,
            kind=event.kind,
            time=event.time,
            state=self.state,
            flags=self.flags,
            resources=self.resources,
            executed_kinds=self._executed_kinds,
            pending_events=self._pending_event_dicts(),
        )

    @property
    def current_time(self) -> int:
        return self._current_time

    def clone(self, *, for_simulation: bool = True) -> Kernel:
        """Deep copy for counterfactual verification at proposal.time."""
        cfg = self.config
        if for_simulation:
            cfg = replace(cfg, use_trace=False, use_causal_ledger=False)

        k = Kernel(
            initial_state=copy.deepcopy(self.state),
            resources=copy.deepcopy(self.resources),
            priors=copy.deepcopy(self.priors),
            config=cfg,
        )
        k.flags = set(self.flags)
        k._current_time = self._current_time
        k._executed_kinds = list(self._executed_kinds)
        k._event_counter = self._event_counter
        k._seq = self._seq

        for item in self._pending_event_dicts():
            event = Event(
                id=item["id"],
                kind=item["kind"],
                time=int(item["time"]),
                priority=int(item.get("priority", 5)),
                seq=int(item.get("seq", 0)),
                payload=dict(item.get("payload", {})),
                cause=list(item.get("cause", [])),
            )
            k._events[event.id] = event
            k._enqueue(event)
        return k

    def _verifier(self):
        from market_causal_engine.vm.verifier import MechanismVerifier

        return MechanismVerifier(
            use_contracts=self.config.use_contracts,
            use_flags=self.config.use_flags,
            use_resources=self.config.use_resources,
        )

    def _verify_proposal_at_time(self, proposal: Proposal) -> VerificationResult:
        """Evaluate contract against kernel state at proposal.time (not submit time)."""
        from market_causal_engine.ir.proposal import VerificationResult

        if proposal.time < self._current_time:
            return VerificationResult(
                proposal_id=proposal.id,
                kind=proposal.kind,
                accepted=False,
                reason_code="proposal_too_late",
                detail=f"proposal_time={proposal.time}<current={self._current_time}",
            )

        sim = self.clone(for_simulation=True)
        target = max(0, proposal.time - 1)
        if sim._current_time < target:
            sim.run(until=target)
        return self._verifier().verify_proposal(sim, proposal)

    def propose(self, proposal: Proposal) -> VerificationResult:
        """Untrusted proposal path: verify at proposal.time, then enqueue if accepted."""
        event_id = proposal.id or self._next_event_id()
        self._record_trace(
            TraceEntry(
                event_id=event_id,
                kind=proposal.kind,
                time=proposal.time,
                action="proposal",
                cause=[f"proposer:{proposal.proposer}"],
                proposal_id=proposal.id,
                proposer=proposal.proposer,
            )
        )

        result = self._verify_proposal_at_time(proposal)
        self._record_trace(
            TraceEntry(
                event_id=event_id,
                kind=proposal.kind,
                time=proposal.time,
                action="verification",
                cause=[f"proposer:{proposal.proposer}"],
                proposal_id=proposal.id,
                proposer=proposal.proposer,
                verification=result.to_dict(),
            )
        )

        if result.accepted:
            target = max(0, proposal.time - 1)
            if self._current_time < target:
                self.run(until=target)
            self.emit(
                kind=proposal.kind,
                payload=proposal.payload,
                at_time=proposal.time,
                priority=proposal.priority,
                cause=[f"proposal:{proposal.id}", f"proposer:{proposal.proposer}"],
            )
        else:
            self._record_trace(
                TraceEntry(
                    event_id=event_id,
                    kind=proposal.kind,
                    time=proposal.time,
                    action="blocked",
                    cause=[f"proposal:{proposal.id}"],
                    blocked_reason=result.detail or result.reason_code,
                    proposal_id=proposal.id,
                    proposer=proposal.proposer,
                    verification=result.to_dict(),
                )
            )
        return result

    def emit(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        delay: int = 0,
        priority: int = 5,
        cause: list[str] | None = None,
        at_time: int | None = None,
    ) -> Event:
        self._seq += 1
        event_time = at_time if at_time is not None else self._current_time + delay
        event = Event(
            id=self._next_event_id(),
            kind=kind,
            time=event_time,
            priority=priority,
            payload=dict(payload or {}),
            cause=list(cause or []),
            seq=self._seq,
        )
        self._events[event.id] = event
        self._enqueue(event)
        return event

    def do(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        delay: int = 0,
        at_time: int | None = None,
    ) -> Event:
        """Inject an intervention event with highest priority."""
        return self.emit(
            kind=kind,
            payload=payload,
            delay=delay,
            priority=0,
            cause=["intervention"],
            at_time=at_time,
        )

    def commit(self, event: Event, patch: dict[str, float]) -> None:
        applied: dict[str, float] = {}
        for key, delta in patch.items():
            if key not in self.state:
                continue
            old = self.state[key]
            if key == "directional_pressure_score":
                headroom = 1.0 - abs(old)
                if delta >= 0:
                    self.state[key] = _clamp(old + delta * max(headroom, 0.05))
                else:
                    self.state[key] = max(-1.0, old + delta * max(headroom, 0.05))
            elif key in OUTCOME_KEYS:
                self.state[key] = _accumulate_outcome(old, delta)
            elif key in STATE_KEYS:
                self.state[key] = _clamp(old + delta)
            else:
                self.state[key] = old + delta
            applied[key] = self.state[key] - old

        if applied:
            self._record_trace(
                TraceEntry(
                    event_id=event.id,
                    kind=event.kind,
                    time=event.time,
                    action="commit",
                    patch=applied,
                    cause=list(event.cause),
                )
            )

    def set_flag(self, flag: str, event: Event) -> None:
        if flag not in self.flags:
            self.flags.add(flag)
            self._record_trace(
                TraceEntry(
                    event_id=event.id,
                    kind=event.kind,
                    time=event.time,
                    action="set_flag",
                    flags_delta={flag: "set"},
                    cause=list(event.cause),
                )
            )

    def clear_flag(self, flag: str, event: Event) -> None:
        if flag in self.flags:
            self.flags.discard(flag)
            self._record_trace(
                TraceEntry(
                    event_id=event.id,
                    kind=event.kind,
                    time=event.time,
                    action="clear_flag",
                    flags_delta={flag: "clear"},
                    cause=list(event.cause),
                )
            )

    def has_flags(self, *flags: str) -> bool:
        return all(flag in self.flags for flag in flags)

    def acquire(self, resource: str, amount: float, event: Event) -> bool:
        if not self.config.use_resources:
            self._record_trace(
                TraceEntry(
                    event_id=event.id,
                    kind=event.kind,
                    time=event.time,
                    action="acquire",
                    resource_delta={resource: -amount},
                    cause=list(event.cause),
                )
            )
            return True

        available = self.resources.get(resource, 0.0)
        if available < amount:
            self._record_trace(
                TraceEntry(
                    event_id=event.id,
                    kind=event.kind,
                    time=event.time,
                    action="blocked",
                    cause=list(event.cause),
                    blocked_reason=f"resource_shortage:{resource}",
                    resource_delta={resource: amount},
                )
            )
            return False

        self.resources[resource] = available - amount
        self._record_trace(
            TraceEntry(
                event_id=event.id,
                kind=event.kind,
                time=event.time,
                action="acquire",
                resource_delta={resource: -amount},
                cause=list(event.cause),
            )
        )
        return True

    def release(self, resource: str, amount: float, event: Event) -> None:
        self.resources[resource] = self.resources.get(resource, 0.0) + amount
        self._record_trace(
            TraceEntry(
                event_id=event.id,
                kind=event.kind,
                time=event.time,
                action="release",
                resource_delta={resource: amount},
                cause=list(event.cause),
            )
        )

    def _trace_blocked(self, event: Event, reason: str) -> None:
        event.status = "blocked"
        self._record_trace(
            TraceEntry(
                event_id=event.id,
                kind=event.kind,
                time=event.time,
                action="blocked",
                cause=list(event.cause),
                blocked_reason=reason,
            )
        )

    def run(self, until: int = 120) -> None:
        while self._queue and self._queue[0][0] <= until:
            event_time, _priority, _seq, event = heapq.heappop(self._queue)
            self._current_time = event_time

            handler = get_handler(event.kind)
            if handler is None:
                self._trace_blocked(event, f"unknown_kind:{event.kind}")
                continue

            if self.config.use_contracts:
                vr = self._verifier().verify_event(self, event)
                self._record_trace(
                    TraceEntry(
                        event_id=event.id,
                        kind=event.kind,
                        time=event.time,
                        action="verification",
                        cause=list(event.cause),
                        verification=vr.to_dict(),
                    )
                )
                if not vr.accepted:
                    self._trace_blocked(event, vr.detail or vr.reason_code)
                    continue
            else:
                spec = get_spec(event.kind)
                if (
                    self.config.use_flags
                    and spec
                    and spec.waits
                    and not self.has_flags(*spec.waits)
                ):
                    missing = [f for f in spec.waits if f not in self.flags]
                    self._trace_blocked(event, f"missing_flags:{','.join(missing)}")
                    continue

            event.status = "executing"
            handler(self, event)
            if event.status == "executing":
                event.status = "executed"
                self._executed_kinds.append(event.kind)
                self._record_trace(
                    TraceEntry(
                        event_id=event.id,
                        kind=event.kind,
                        time=event.time,
                        action="executed",
                        cause=list(event.cause),
                    )
                )
                self._save_snapshot(event)

    def prior(self, mechanism: str, key: str, default: float = 0.0) -> float:
        return float(self.priors.get(mechanism, {}).get(key, default))

    def dominant_path(self) -> list[str]:
        """Phase 1: approximate path from executed event kinds in order."""
        seen: list[str] = []
        for kind in self._executed_kinds:
            if not seen or seen[-1] != kind:
                seen.append(kind)
        return seen

    def to_result(self, scenario_id: str = "", world_id: str = "W0") -> dict[str, Any]:
        final_risk = {
            OUTCOME_DISPLAY[key]: round(self.state[key], 4)
            for key in OUTCOME_KEYS
        }
        bottlenecks: dict[str, int] = {}
        for entry in self.trace:
            if entry.action == "blocked" and entry.blocked_reason:
                if entry.blocked_reason.startswith("resource_shortage:"):
                    resource = entry.blocked_reason.split(":", 1)[1]
                    bottlenecks[resource] = bottlenecks.get(resource, 0) + 1

        out: dict[str, Any] = {
            "scenario_id": scenario_id,
            "world_id": world_id,
            "final_state": {k: round(v, 4) for k, v in self.state.items()},
            "final_risk": final_risk,
            "dominant_path": self.dominant_path(),
            "active_flags": sorted(self.flags),
            "resource_bottlenecks": [
                {"resource": r, "failures": c}
                for r, c in sorted(bottlenecks.items(), key=lambda x: -x[1])
            ],
            "remaining_resources": {k: round(v, 2) for k, v in self.resources.items()},
            "kernel_config": self.config.to_dict(),
            "trace": [
                {
                    "event_id": e.event_id,
                    "kind": e.kind,
                    "time": e.time,
                    "action": e.action,
                    "patch": e.patch,
                    "flags_delta": e.flags_delta,
                    "resource_delta": e.resource_delta,
                    "cause": e.cause,
                    "blocked_reason": e.blocked_reason,
                    "proposal_id": e.proposal_id,
                    "verification": e.verification,
                    "proposer": e.proposer,
                    "ledger_entry_id": e.ledger_entry_id,
                }
                for e in self.trace
            ],
        }
        if self.ledger is not None:
            out["causal_ledger"] = self.ledger.to_dict()
        return out
