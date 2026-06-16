"""Step C: point-in-time data hardening — temporal envelopes, audit, atom↔PIT bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.lookahead import LookAheadPolicy, validate_atom
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope
from market_causal_engine.platform.quality import validate_pit_record

FIXTURE_INGESTED_TIME = "1970-01-01T00:00:00+00:00"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class CaseTimeAxis:
    """Maps case-study minute timeline (t=0) to wall-clock ISO timestamps."""

    origin_iso: str
    unit: str = "minutes"
    event_date: str | None = None

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> CaseTimeAxis:
        axis = manifest.get("time_axis") or {}
        origin = axis.get("origin_timestamp_et") or axis.get("origin_timestamp_utc")
        event_date = manifest.get("event_date") or manifest.get("aligned_filing_date") or manifest.get("filing_date")
        if not origin and event_date:
            # Catalog / legacy fallback: after-hours release proxy
            origin = f"{event_date}T21:00:00+00:00"
        if not origin:
            raise ValueError("manifest missing time_axis.origin_timestamp_et and event_date")
        return cls(origin_iso=str(origin), unit=str(axis.get("unit", "minutes")), event_date=event_date)

    def minute_to_iso(self, minute: int) -> str:
        origin = _parse_iso(self.origin_iso)
        dt = origin + timedelta(minutes=int(minute))
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    def as_of_iso(self, as_of_minutes: int) -> str:
        return self.minute_to_iso(as_of_minutes)


def atom_published_minute(atom: MarketAtom) -> int:
    if atom.published_at is not None:
        return int(atom.published_at)
    return int(atom.time)


def atom_observed_minute(atom: MarketAtom) -> int:
    return int(atom.time)


def build_atom_temporal(atom: MarketAtom, axis: CaseTimeAxis) -> dict[str, str]:
    """Full PIT temporal envelope for a feed atom."""
    pub_min = atom_published_minute(atom)
    obs_min = atom_observed_minute(atom)
    revision = str(atom.metadata.get("revision_id", "initial"))
    published_iso = axis.minute_to_iso(pub_min)
    observed_iso = axis.minute_to_iso(obs_min)
    ingested_raw = atom.metadata.get("ingested_time")
    if ingested_raw and str(ingested_raw) != FIXTURE_INGESTED_TIME:
        ingested = str(ingested_raw)
    else:
        # Fixture atoms: default ingest at publication so published <= ingested.
        ingested = published_iso if _parse_iso(published_iso) >= _parse_iso(observed_iso) else observed_iso
    return {
        "observed_time": observed_iso,
        "published_time": published_iso,
        "ingested_time": ingested,
        "revision_id": revision,
    }


def enrich_atom_temporal(atom: MarketAtom, axis: CaseTimeAxis) -> MarketAtom:
    """Attach metadata.temporal when missing (non-destructive copy)."""
    if isinstance(atom.metadata.get("temporal"), dict) and atom.metadata["temporal"].get("published_time"):
        return atom
    temporal = build_atom_temporal(atom, axis)
    meta = dict(atom.metadata)
    meta["temporal"] = temporal
    return MarketAtom(
        atom_id=atom.atom_id,
        text=atom.text,
        source=atom.source,
        time=atom.time,
        tags=list(atom.tags),
        metadata=meta,
        published_at=atom.published_at,
    )


def enrich_atoms_temporal(atoms: list[MarketAtom], axis: CaseTimeAxis) -> list[MarketAtom]:
    return [enrich_atom_temporal(a, axis) for a in atoms]


def source_kind_for_atom(atom: MarketAtom) -> SourceKind:
    src = (atom.source or "").lower()
    sc = str(atom.metadata.get("source_class", "")).lower()
    extracted = str(atom.metadata.get("extracted_by", "")).lower()
    if sc == "primary_filing" or src in {"8-k", "sec", "earnings_call_transcript", "guidance"}:
        return SourceKind.SEC_EDGAR
    if extracted in {"market_move", "options_vol", "intraday_vol"} or "options" in atom.tags:
        return SourceKind.MARKET_OPTIONS
    if sc == "news_wire" or "news" in src or extracted in {"sector_etf", "analyst_downgrade"}:
        return SourceKind.NEWS_RSS
    if sc == "macro_release" or src in {"fomc", "cpi", "bls", "fred"}:
        return SourceKind.MACRO_FRED
    return SourceKind.MANUAL


def atom_to_pit_record(
    atom: MarketAtom,
    *,
    axis: CaseTimeAxis,
    ticker: str = "UNKNOWN",
    record_id: str | None = None,
) -> PITRecord:
    enriched = enrich_atom_temporal(atom, axis)
    temporal_dict = enriched.metadata["temporal"]
    temporal = TemporalEnvelope.from_dict(temporal_dict)
    rid = record_id or f"atom_{atom.atom_id}"
    return PITRecord(
        record_id=rid,
        source_kind=source_kind_for_atom(atom),
        source_id=f"{ticker}:{atom.atom_id}",
        payload={
            "atom_id": atom.atom_id,
            "text": atom.text,
            "source": atom.source,
            "tags": atom.tags,
            "metadata": {k: v for k, v in atom.metadata.items() if k != "temporal"},
        },
        temporal=temporal,
        metadata={"ticker": ticker, "timeline_minute": atom_published_minute(atom)},
    )


@dataclass
class PITViolation:
    atom_id: str
    code: str
    severity: str  # error | warning
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class PITAuditReport:
    as_of_minutes: int
    as_of_iso: str
    total_atoms: int = 0
    admissible_atoms: int = 0
    envelope_complete: int = 0
    violations: list[PITViolation] = field(default_factory=list)

    @property
    def envelope_coverage(self) -> float:
        if self.admissible_atoms == 0:
            return 1.0
        return self.envelope_complete / self.admissible_atoms

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        by_code: dict[str, int] = {}
        for v in self.violations:
            by_code[v.code] = by_code.get(v.code, 0) + 1
        return {
            "as_of_minutes": self.as_of_minutes,
            "as_of_iso": self.as_of_iso,
            "total_atoms": self.total_atoms,
            "admissible_atoms": self.admissible_atoms,
            "envelope_complete": self.envelope_complete,
            "envelope_coverage": round(self.envelope_coverage, 4),
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": sum(1 for v in self.violations if v.severity == "warning"),
            "violations_by_code": by_code,
            "violations": [v.to_dict() for v in self.violations],
        }


def audit_atom_pit(
    atom: MarketAtom,
    *,
    axis: CaseTimeAxis,
    as_of_minutes: int,
    policy: LookAheadPolicy | None = None,
    require_envelope: bool = True,
) -> list[PITViolation]:
    policy = policy or LookAheadPolicy()
    violations: list[PITViolation] = []
    aid = atom.atom_id

    la = validate_atom(atom, as_of=as_of_minutes, policy=policy)
    if not la.accepted:
        violations.append(
            PITViolation(
                atom_id=aid,
                code=la.reason_code,
                severity="error",
                message=la.detail or la.reason_code,
            )
        )
        return violations

    enriched = enrich_atom_temporal(atom, axis)
    temporal_dict = enriched.metadata.get("temporal") or {}
    missing = [f for f in ("observed_time", "published_time", "ingested_time") if not temporal_dict.get(f)]
    if missing and require_envelope:
        violations.append(
            PITViolation(
                atom_id=aid,
                code="missing_temporal_envelope",
                severity="error",
                message=f"missing fields: {', '.join(missing)}",
            )
        )
        return violations

    record = atom_to_pit_record(enriched, axis=axis)
    as_of_iso = axis.as_of_iso(as_of_minutes)
    for issue in validate_pit_record(record, as_of_time=as_of_iso):
        violations.append(
            PITViolation(
                atom_id=aid,
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
            )
        )

    if atom.published_at is None:
        violations.append(
            PITViolation(
                atom_id=aid,
                code="missing_published_at",
                severity="warning",
                message="published_at not set; inferred from time",
            )
        )

    return violations


def audit_atoms_pit(
    atoms: list[MarketAtom],
    *,
    axis: CaseTimeAxis,
    as_of_minutes: int,
    policy: LookAheadPolicy | None = None,
    admissible_only: bool = True,
) -> PITAuditReport:
    policy = policy or LookAheadPolicy()
    as_of_iso = axis.as_of_iso(as_of_minutes)
    report = PITAuditReport(as_of_minutes=as_of_minutes, as_of_iso=as_of_iso, total_atoms=len(atoms))

    for atom in atoms:
        la = validate_atom(atom, as_of=as_of_minutes, policy=policy)
        if admissible_only and not la.accepted:
            continue
        report.admissible_atoms += 1
        atom_violations = audit_atom_pit(atom, axis=axis, as_of_minutes=as_of_minutes, policy=policy)
        report.violations.extend(atom_violations)
        hard = [v for v in atom_violations if v.severity == "error"]
        if not hard:
            report.envelope_complete += 1

    return report


def attach_pit_audit(
    result: dict[str, Any],
    *,
    manifest: dict[str, Any],
    atoms: list[MarketAtom],
    as_of_minutes: int,
    policy: LookAheadPolicy | None = None,
) -> dict[str, Any]:
    """Attach pit_audit block to replay / case-study results."""
    try:
        axis = CaseTimeAxis.from_manifest(manifest)
    except ValueError as exc:
        result["pit_audit"] = {
            "passed": False,
            "error_count": 1,
            "violations": [{"atom_id": "", "code": "missing_time_axis", "severity": "error", "message": str(exc)}],
        }
        return result

    policy = policy or LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    audit = audit_atoms_pit(atoms, axis=axis, as_of_minutes=as_of_minutes, policy=policy)
    result["pit_audit"] = audit.to_dict()
    result["pit_audit"]["time_axis_origin"] = axis.origin_iso
    return result


def summarize_pit_compliance(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return {"n": 0, "all_passed": True}
    passed = sum(1 for r in reports if r.get("passed"))
    return {
        "n": len(reports),
        "passed": passed,
        "failed": len(reports) - passed,
        "all_passed": passed == len(reports),
        "mean_envelope_coverage": round(
            sum(float(r.get("envelope_coverage", 0.0)) for r in reports) / len(reports),
            4,
        ),
    }


def audit_case_study(case_id: str, *, as_of_minutes: int | None = None) -> dict[str, Any]:
    from market_causal_engine.case_study import load_case_manifest
    from market_causal_engine.evidence import load_atoms

    manifest = load_case_manifest(case_id)
    root = manifest["_root"]
    horizon = as_of_minutes if as_of_minutes is not None else int(manifest.get("default_until", 120))
    atoms = load_atoms(f"{root}/{manifest.get('atoms_path', 'atoms.jsonl')}")
    axis = CaseTimeAxis.from_manifest(manifest)
    policy = LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    report = audit_atoms_pit(atoms, axis=axis, as_of_minutes=horizon, policy=policy)
    out = report.to_dict()
    out["case_id"] = case_id
    out["time_axis_origin"] = axis.origin_iso
    return out
