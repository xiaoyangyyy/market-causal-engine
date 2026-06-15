"""Reproducibility metadata attached to every pipeline run and API response."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MODEL_VERSION = "0.5.0"
_RULESET_VERSION = "compiler_v0.1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_id(prefix: str = "run") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{prefix}_{ts}_{short}"


@dataclass
class RunManifest:
    run_id: str
    model_version: str = _MODEL_VERSION
    ruleset_version: str = _RULESET_VERSION
    data_snapshot_id: str = ""
    source_hashes: dict[str, str] = field(default_factory=dict)
    as_of_time: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    stages: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # running | succeeded | failed | partial
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_version": self.model_version,
            "ruleset_version": self.ruleset_version,
            "data_snapshot_id": self.data_snapshot_id,
            "source_hashes": self.source_hashes,
            "as_of_time": self.as_of_time,
            "created_at": self.created_at,
            "stages": self.stages,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunManifest:
        return cls(
            run_id=str(data["run_id"]),
            model_version=str(data.get("model_version", _MODEL_VERSION)),
            ruleset_version=str(data.get("ruleset_version", _RULESET_VERSION)),
            data_snapshot_id=str(data.get("data_snapshot_id", "")),
            source_hashes=dict(data.get("source_hashes", {})),
            as_of_time=str(data.get("as_of_time", "")),
            created_at=str(data.get("created_at", _utc_now_iso())),
            stages=list(data.get("stages", [])),
            status=str(data.get("status", "running")),
            error=data.get("error"),
        )

    def add_stage(self, name: str, *, status: str, detail: dict[str, Any] | None = None) -> None:
        self.stages.append(
            {
                "name": name,
                "status": status,
                "at": _utc_now_iso(),
                "detail": detail or {},
            }
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> RunManifest:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_provenance(
    *,
    run_id: str,
    data_snapshot_id: str,
    source_hashes: dict[str, str],
    as_of_time: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model_version": _MODEL_VERSION,
        "ruleset_version": _RULESET_VERSION,
        "data_snapshot_id": data_snapshot_id,
        "source_hashes": source_hashes,
        "as_of_time": as_of_time,
        "created_at": _utc_now_iso(),
    }


def trace_determinism_hash(trace: list[dict[str, Any]]) -> str:
    raw = json.dumps(trace, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
