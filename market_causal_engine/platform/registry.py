"""Filing version registry for EDGAR diff detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class FilingVersion:
    ticker: str
    accession_number: str
    form_type: str
    filing_date: str
    content_hash: str
    document_url: str | None = None
    is_amended: bool = False
    changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "content_hash": self.content_hash,
            "document_url": self.document_url,
            "is_amended": self.is_amended,
            "changed": self.changed,
        }


class FilingRegistry(Protocol):
    def upsert_filing(self, filing: FilingVersion) -> FilingVersion:
        ...

    def get_filing_hash(self, ticker: str, accession_number: str) -> str | None:
        ...


@dataclass
class BackfillJob:
    job_id: str
    job_type: str
    status: str = "pending"
    cursor: dict[str, Any] | None = None
    total: int = 0
    completed: int = 0
    failed: int = 0
    error: str | None = None
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "cursor": self.cursor or {},
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "error": self.error,
            "config": self.config or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackfillJob:
        return cls(
            job_id=str(data["job_id"]),
            job_type=str(data["job_type"]),
            status=str(data.get("status", "pending")),
            cursor=dict(data.get("cursor", {})),
            total=int(data.get("total", 0)),
            completed=int(data.get("completed", 0)),
            failed=int(data.get("failed", 0)),
            error=data.get("error"),
            config=dict(data.get("config", {})),
        )


class BackfillStore(Protocol):
    def create_job(self, job: BackfillJob) -> BackfillJob:
        ...

    def update_job(self, job: BackfillJob) -> None:
        ...

    def get_job(self, job_id: str) -> BackfillJob | None:
        ...

    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> list[BackfillJob]:
        ...
