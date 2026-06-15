"""Base ingestion contracts for production data adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from market_causal_engine.platform.pit import PITRecord, SourceKind


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class IngestContext:
    """Runtime context passed to every ingestor."""

    run_id: str
    as_of_time: str
    tickers: list[str] = field(default_factory=list)
    force_refresh: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    source_kind: SourceKind
    records: list[PITRecord] = field(default_factory=list)
    fetched: int = 0
    stored: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors or self.stored > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind.value,
            "fetched": self.fetched,
            "stored": self.stored,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "record_ids": [r.record_id for r in self.records],
        }


class Ingestor(ABC):
    """Pull external data and emit PIT records."""

    source_kind: SourceKind

    @abstractmethod
    def ingest(self, ctx: IngestContext) -> IngestResult:
        ...
