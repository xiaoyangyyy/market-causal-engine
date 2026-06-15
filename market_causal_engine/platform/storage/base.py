"""Extended storage interface — PIT records, filings, backfill, macro series."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from market_causal_engine.platform.pit import PITRecord, SourceKind
from market_causal_engine.platform.provenance import RunManifest
from market_causal_engine.platform.registry import BackfillJob, BackfillStore, FilingRegistry, FilingVersion


class StorageBackend(ABC):
    @abstractmethod
    def save_records(self, snapshot_id: str, records: list[PITRecord]) -> int:
        ...

    @abstractmethod
    def list_records(
        self,
        *,
        snapshot_id: str | None = None,
        source_kind: SourceKind | None = None,
        limit: int = 100,
    ) -> list[PITRecord]:
        ...

    @abstractmethod
    def save_manifest(self, manifest: RunManifest) -> None:
        ...

    @abstractmethod
    def load_manifest(self, run_id: str) -> RunManifest | None:
        ...

    @abstractmethod
    def latest_snapshot_id(self) -> str | None:
        ...

    @abstractmethod
    def freshness_report(self) -> dict[str, Any]:
        ...


class PlatformStore(StorageBackend, FilingRegistry, BackfillStore, ABC):
    @abstractmethod
    def ensure_schema(self) -> None:
        ...

    @abstractmethod
    def upsert_filing(self, filing: FilingVersion) -> FilingVersion:
        ...

    @abstractmethod
    def get_filing_hash(self, ticker: str, accession_number: str) -> str | None:
        ...

    @abstractmethod
    def create_job(self, job: BackfillJob) -> BackfillJob:
        ...

    @abstractmethod
    def update_job(self, job: BackfillJob) -> None:
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> BackfillJob | None:
        ...

    @abstractmethod
    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> list[BackfillJob]:
        ...

    @abstractmethod
    def upsert_macro_point(
        self,
        *,
        series_id: str,
        source: str,
        observation_date: str,
        value: float | None,
        revision_id: str,
        published_time: str,
        content_hash: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Return True if new revision inserted."""

    @abstractmethod
    def list_macro_revisions(self, series_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        ...
