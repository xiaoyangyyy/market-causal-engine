"""Append-only causal ledger with content-addressed entries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from market_causal_engine.ledger.snapshot import CausalSnapshot


def _entry_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class LedgerEntry:
    entry_id: str
    seq: int
    event_id: str
    kind: str
    time: int
    action: str
    cause: list[str] = field(default_factory=list)
    patch: dict[str, float] = field(default_factory=dict)
    flags_delta: dict[str, str] = field(default_factory=dict)
    resource_delta: dict[str, float] = field(default_factory=dict)
    blocked_reason: str | None = None
    proposal_id: str | None = None
    verification: dict[str, Any] | None = None
    proposer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "entry_id": self.entry_id,
            "seq": self.seq,
            "event_id": self.event_id,
            "kind": self.kind,
            "time": self.time,
            "action": self.action,
            "cause": self.cause,
        }
        if self.patch:
            d["patch"] = self.patch
        if self.flags_delta:
            d["flags_delta"] = self.flags_delta
        if self.resource_delta:
            d["resource_delta"] = self.resource_delta
        if self.blocked_reason:
            d["blocked_reason"] = self.blocked_reason
        if self.proposal_id:
            d["proposal_id"] = self.proposal_id
        if self.verification:
            d["verification"] = self.verification
        if self.proposer:
            d["proposer"] = self.proposer
        return d


class CausalLedger:
    """Append-only log + snapshots indexed by executed event_id."""

    def __init__(self, ledger_id: str = "main"):
        self.ledger_id = ledger_id
        self.entries: list[LedgerEntry] = []
        self.snapshots: dict[str, CausalSnapshot] = {}
        self._seq = 0
        self._snapshot_counter = 0

    def append(
        self,
        *,
        event_id: str,
        kind: str,
        time: int,
        action: str,
        cause: list[str] | None = None,
        patch: dict[str, float] | None = None,
        flags_delta: dict[str, str] | None = None,
        resource_delta: dict[str, float] | None = None,
        blocked_reason: str | None = None,
        proposal_id: str | None = None,
        verification: dict[str, Any] | None = None,
        proposer: str | None = None,
    ) -> LedgerEntry:
        self._seq += 1
        payload = {
            "seq": self._seq,
            "event_id": event_id,
            "kind": kind,
            "time": time,
            "action": action,
        }
        entry = LedgerEntry(
            entry_id=_entry_hash(payload),
            seq=self._seq,
            event_id=event_id,
            kind=kind,
            time=time,
            action=action,
            cause=list(cause or []),
            patch=dict(patch or {}),
            flags_delta=dict(flags_delta or {}),
            resource_delta=dict(resource_delta or {}),
            blocked_reason=blocked_reason,
            proposal_id=proposal_id,
            verification=verification,
            proposer=proposer,
        )
        self.entries.append(entry)
        return entry

    def save_snapshot(
        self,
        event_id: str,
        kind: str,
        time: int,
        state: dict[str, float],
        flags: set[str],
        resources: dict[str, float],
        executed_kinds: list[str],
        pending_events: list[dict[str, Any]] | None = None,
    ) -> CausalSnapshot:
        self._snapshot_counter += 1
        snap = CausalSnapshot(
            snapshot_id=f"SNAP{self._snapshot_counter}",
            event_id=event_id,
            kind=kind,
            time=time,
            state=dict(state),
            flags=sorted(flags),
            resources=dict(resources),
            executed_kinds=list(executed_kinds),
            pending_events=list(pending_events or []),
        )
        self.snapshots[event_id] = snap
        return snap

    def get_snapshot(self, event_id: str) -> CausalSnapshot | None:
        return self.snapshots.get(event_id)

    def snapshot_before_kind(self, kind: str) -> CausalSnapshot | None:
        """Return snapshot from the executed event immediately before first `kind`."""
        executed_ids = [
            e.event_id for e in self.entries if e.action == "executed"
        ]
        target_idx = None
        for i, entry in enumerate(self.entries):
            if entry.action == "executed" and entry.kind == kind:
                if i > 0:
                    prev = self.entries[i - 1]
                    if prev.action == "executed":
                        target_idx = prev.event_id
                break
        if target_idx:
            return self.snapshots.get(target_idx)
        for eid in reversed(executed_ids):
            snap = self.snapshots.get(eid)
            if snap and snap.kind != kind:
                return snap
        return None

    def executed_path(self) -> list[str]:
        kinds: list[str] = []
        for entry in self.entries:
            if entry.action == "executed":
                if not kinds or kinds[-1] != entry.kind:
                    kinds.append(entry.kind)
        return kinds

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "entries": [e.to_dict() for e in self.entries],
            "snapshots": {k: v.to_dict() for k, v in self.snapshots.items()},
            "executed_path": self.executed_path(),
        }

    def save(self, path: str) -> None:
        from pathlib import Path
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CausalLedger:
        ledger = cls(ledger_id=data.get("ledger_id", "imported"))
        for entry_dict in data.get("entries", []):
            ledger.append(
                event_id=entry_dict.get("event_id", ""),
                kind=entry_dict.get("kind", ""),
                time=int(entry_dict.get("time", 0)),
                action=entry_dict.get("action", ""),
                cause=entry_dict.get("cause"),
                patch=entry_dict.get("patch"),
                flags_delta=entry_dict.get("flags_delta"),
                resource_delta=entry_dict.get("resource_delta"),
                blocked_reason=entry_dict.get("blocked_reason"),
                proposal_id=entry_dict.get("proposal_id"),
                verification=entry_dict.get("verification"),
                proposer=entry_dict.get("proposer"),
            )
        for eid, snap_dict in data.get("snapshots", {}).items():
            ledger.snapshots[eid] = CausalSnapshot.from_dict(snap_dict)
        return ledger

    @classmethod
    def from_trace(cls, trace: list[dict[str, Any]], ledger_id: str = "imported") -> CausalLedger:
        ledger = cls(ledger_id=ledger_id)
        for t in trace:
            ledger.append(
                event_id=t.get("event_id", ""),
                kind=t.get("kind", ""),
                time=int(t.get("time", 0)),
                action=t.get("action", ""),
                cause=t.get("cause"),
                patch=t.get("patch"),
                flags_delta=t.get("flags_delta"),
                resource_delta=t.get("resource_delta"),
                blocked_reason=t.get("blocked_reason"),
                proposal_id=t.get("proposal_id"),
                verification=t.get("verification"),
                proposer=t.get("proposer"),
            )
        return ledger
