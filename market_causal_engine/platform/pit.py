"""Point-in-time data contracts for production ingestion and replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def content_hash(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class SourceKind(str, Enum):
    SEC_EDGAR = "sec_edgar"
    MACRO_FRED = "macro_fred"
    MACRO_BLS = "macro_bls"
    MACRO_FOMC = "macro_fomc"
    NEWS_RSS = "news_rss"
    NEWS_API = "news_api"
    MARKET_PRICE = "market_price"
    MARKET_OPTIONS = "market_options"
    MANUAL = "manual"


@dataclass(frozen=True)
class TemporalEnvelope:
    """When facts occurred vs when we learned them — required on all PIT records."""

    observed_time: str  # ISO8601 UTC — underlying event time
    published_time: str  # ISO8601 UTC — source publication time
    ingested_time: str  # ISO8601 UTC — pipeline receipt time
    revision_id: str = "initial"  # BLS/FRED restatement id

    def to_dict(self) -> dict[str, str]:
        return {
            "observed_time": self.observed_time,
            "published_time": self.published_time,
            "ingested_time": self.ingested_time,
            "revision_id": self.revision_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemporalEnvelope:
        return cls(
            observed_time=str(data["observed_time"]),
            published_time=str(data["published_time"]),
            ingested_time=str(data.get("ingested_time", _utc_now_iso())),
            revision_id=str(data.get("revision_id", "initial")),
        )

    @classmethod
    def now(cls, *, observed: str | None = None, published: str | None = None) -> TemporalEnvelope:
        now = _utc_now_iso()
        return cls(
            observed_time=observed or now,
            published_time=published or now,
            ingested_time=now,
        )


@dataclass
class PITRecord:
    """Versioned, point-in-time storage unit."""

    record_id: str
    source_kind: SourceKind
    source_id: str  # e.g. "NFLX:8-K:0000320193-22-000012"
    payload: dict[str, Any]
    temporal: TemporalEnvelope
    schema_version: str = "pit_v1"
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = content_hash(
                {"source_id": self.source_id, "payload": self.payload, "revision_id": self.temporal.revision_id}
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "payload": self.payload,
            "temporal": self.temporal.to_dict(),
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PITRecord:
        return cls(
            record_id=str(data["record_id"]),
            source_kind=SourceKind(str(data["source_kind"])),
            source_id=str(data["source_id"]),
            payload=dict(data["payload"]),
            temporal=TemporalEnvelope.from_dict(data["temporal"]),
            schema_version=str(data.get("schema_version", "pit_v1")),
            content_hash=str(data.get("content_hash", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def admissible_at(self, as_of_iso: str) -> bool:
        """Record may enter causal kernel only if published before as_of."""
        return self.temporal.published_time <= as_of_iso
