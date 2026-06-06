"""Point-in-time kernel snapshots for fork/replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CausalSnapshot:
    """Immutable checkpoint after an executed event."""

    snapshot_id: str
    event_id: str
    kind: str
    time: int
    state: dict[str, float]
    flags: list[str]
    resources: dict[str, float]
    executed_kinds: list[str]
    pending_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "event_id": self.event_id,
            "kind": self.kind,
            "time": self.time,
            "state": self.state,
            "flags": self.flags,
            "resources": self.resources,
            "executed_kinds": list(self.executed_kinds),
            "pending_events": self.pending_events,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CausalSnapshot:
        return cls(
            snapshot_id=data["snapshot_id"],
            event_id=data["event_id"],
            kind=data["kind"],
            time=int(data["time"]),
            state=dict(data["state"]),
            flags=list(data.get("flags", [])),
            resources=dict(data.get("resources", {})),
            executed_kinds=list(data.get("executed_kinds", [])),
            pending_events=list(data.get("pending_events", [])),
        )
