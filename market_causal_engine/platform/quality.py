"""Data quality gates for ingestion and compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from market_causal_engine.platform.pit import PITRecord

REQUIRED_PIT_FIELDS = ("observed_time", "published_time", "ingested_time")


@dataclass
class QualityIssue:
    severity: str  # error | warning
    code: str
    message: str
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "record_id": self.record_id,
        }


@dataclass
class QualityReport:
    accepted: int = 0
    rejected: int = 0
    warnings: int = 0
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.rejected == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "warnings": self.warnings,
            "issues": [i.to_dict() for i in self.issues],
        }


def _parse_iso(ts: str) -> datetime | None:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def validate_pit_record(record: PITRecord, *, as_of_time: str | None = None) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    temporal = record.temporal.to_dict()

    for field_name in REQUIRED_PIT_FIELDS:
        if not temporal.get(field_name):
            issues.append(
                QualityIssue(
                    severity="error",
                    code="missing_temporal_field",
                    message=f"Missing {field_name}",
                    record_id=record.record_id,
                )
            )

    observed = _parse_iso(temporal.get("observed_time", ""))
    published = _parse_iso(temporal.get("published_time", ""))
    ingested = _parse_iso(temporal.get("ingested_time", ""))

    if observed and published and observed > published:
        issues.append(
            QualityIssue(
                severity="warning",
                code="observed_after_published",
                message="observed_time is after published_time",
                record_id=record.record_id,
            )
        )

    if published and ingested and published > ingested:
        issues.append(
            QualityIssue(
                severity="warning",
                code="published_after_ingested",
                message="published_time is after ingested_time (clock skew?)",
                record_id=record.record_id,
            )
        )

    if as_of_time and not record.admissible_at(as_of_time):
        issues.append(
            QualityIssue(
                severity="error",
                code="lookahead_violation",
                message=f"published_time after as_of_time {as_of_time}",
                record_id=record.record_id,
            )
        )

    if not record.payload:
        issues.append(
            QualityIssue(
                severity="error",
                code="empty_payload",
                message="Record payload is empty",
                record_id=record.record_id,
            )
        )

    return issues


def validate_records(
    records: list[PITRecord],
    *,
    as_of_time: str | None = None,
    max_staleness_hours: float = 72.0,
) -> QualityReport:
    report = QualityReport()
    now = datetime.now(timezone.utc)

    for record in records:
        issues = validate_pit_record(record, as_of_time=as_of_time)
        hard_errors = [i for i in issues if i.severity == "error"]
        if hard_errors:
            report.rejected += 1
            report.issues.extend(hard_errors)
            continue

        ingested = _parse_iso(record.temporal.ingested_time)
        if ingested:
            age_hours = (now - ingested.astimezone(timezone.utc)).total_seconds() / 3600
            if age_hours > max_staleness_hours:
                report.warnings += 1
                report.issues.append(
                    QualityIssue(
                        severity="warning",
                        code="stale_record",
                        message=f"Record ingested {age_hours:.1f}h ago",
                        record_id=record.record_id,
                    )
                )

        report.warnings += len([i for i in issues if i.severity == "warning"])
        report.issues.extend([i for i in issues if i.severity == "warning"])
        report.accepted += 1

    return report
