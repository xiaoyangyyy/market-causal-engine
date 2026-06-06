"""Observation schema and dataset loader for Phase 8 calibration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Observation:
    scenario_id: str
    world_id: str
    time_bucket: str  # e.g. "t70_80" or "final"
    key: str  # standardized key (see evidence_types.ObservationKey)
    value: float
    weight: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Observation":
        return cls(
            scenario_id=d.get("scenario_id", ""),
            world_id=d.get("world_id", "W0"),
            time_bucket=d.get("time_bucket", "final"),
            key=d["key"],
            value=float(d["value"]),
            weight=float(d.get("weight", 1.0)),
            meta=dict(d.get("meta", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "world_id": self.world_id,
            "time_bucket": self.time_bucket,
            "key": self.key,
            "value": self.value,
            "weight": self.weight,
        }
        if self.meta:
            out["meta"] = dict(self.meta)
        return out


class Dataset:
    def __init__(self, observations: list[Observation] | None = None):
        self.observations = observations or []

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "Dataset":
        p = Path(path)
        obs: list[Observation] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obs.append(Observation.from_dict(json.loads(line)))
        return cls(obs)

    def filter(self, *, scenario_id: str, world_id: str) -> "Dataset":
        return Dataset(
            [o for o in self.observations if o.scenario_id == scenario_id and o.world_id == world_id]
        )

