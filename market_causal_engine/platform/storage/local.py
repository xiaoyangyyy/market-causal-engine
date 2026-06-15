"""Local file-backed platform store for development and CI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.platform.pit import PITRecord, SourceKind
from market_causal_engine.platform.provenance import RunManifest
from market_causal_engine.platform.registry import BackfillJob, FilingVersion
from market_causal_engine.platform.storage.base import PlatformStore


def default_store_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "platform_store"


class LocalPlatformStore(PlatformStore):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_store_root()
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("snapshots", "runs", "backfill", "filings", "macro"):
            (self.root / sub).mkdir(exist_ok=True)

    def ensure_schema(self) -> None:
        return

    def _snapshot_path(self, snapshot_id: str) -> Path:
        return self.root / "snapshots" / snapshot_id

    def save_records(self, snapshot_id: str, records: list[PITRecord]) -> int:
        snap_dir = self._snapshot_path(snapshot_id)
        snap_dir.mkdir(parents=True, exist_ok=True)
        index_path = snap_dir / "index.jsonl"
        stored = 0
        with index_path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                stored += 1
        meta = {
            "snapshot_id": snapshot_id,
            "record_count": self._count_snapshot(snapshot_id),
            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        (snap_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return stored

    def _count_snapshot(self, snapshot_id: str) -> int:
        index_path = self._snapshot_path(snapshot_id) / "index.jsonl"
        if not index_path.exists():
            return 0
        return sum(1 for _ in index_path.open(encoding="utf-8"))

    def list_records(
        self,
        *,
        snapshot_id: str | None = None,
        source_kind: SourceKind | None = None,
        limit: int = 100,
    ) -> list[PITRecord]:
        sid = snapshot_id or self.latest_snapshot_id()
        if not sid:
            return []
        index_path = self._snapshot_path(sid) / "index.jsonl"
        if not index_path.exists():
            return []
        out: list[PITRecord] = []
        for line in index_path.open(encoding="utf-8"):
            if not line.strip():
                continue
            record = PITRecord.from_dict(json.loads(line))
            if source_kind and record.source_kind != source_kind:
                continue
            out.append(record)
            if len(out) >= limit:
                break
        return out

    def save_manifest(self, manifest: RunManifest) -> None:
        manifest.save(self.root / "runs" / f"{manifest.run_id}.json")

    def load_manifest(self, run_id: str) -> RunManifest | None:
        path = self.root / "runs" / f"{run_id}.json"
        if not path.exists():
            return None
        return RunManifest.load(path)

    def latest_snapshot_id(self) -> str | None:
        snap_root = self.root / "snapshots"
        dirs = [d for d in snap_root.iterdir() if d.is_dir()]
        if not dirs:
            return None
        return sorted(dirs, key=lambda d: d.name)[-1].name

    def freshness_report(self) -> dict[str, Any]:
        snap_id = self.latest_snapshot_id()
        if not snap_id:
            return {"backend": "local", "latest_snapshot_id": None, "sources": {}, "stale": True}
        meta_path = self._snapshot_path(snap_id) / "meta.json"
        updated_at = None
        if meta_path.exists():
            updated_at = json.loads(meta_path.read_text(encoding="utf-8")).get("updated_at")
        records = self.list_records(snapshot_id=snap_id, limit=10_000)
        by_source: dict[str, str | None] = {}
        for rec in records:
            key = rec.source_kind.value
            pub = rec.temporal.published_time
            if key not in by_source or pub > (by_source[key] or ""):
                by_source[key] = pub
        return {
            "backend": "local",
            "latest_snapshot_id": snap_id,
            "updated_at": updated_at,
            "sources": by_source,
            "record_count": len(records),
            "stale": updated_at is None,
        }

    def _filings_index(self) -> Path:
        return self.root / "filings" / "index.json"

    def upsert_filing(self, filing: FilingVersion) -> FilingVersion:
        index_path = self._filings_index()
        data: dict[str, dict[str, Any]] = {}
        if index_path.exists():
            data = json.loads(index_path.read_text(encoding="utf-8"))
        key = f"{filing.ticker}:{filing.accession_number}"
        prev = data.get(key)
        changed = prev is None or prev.get("content_hash") != filing.content_hash
        is_amended = prev is not None and changed
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        entry = filing.to_dict()
        entry["first_seen_at"] = prev.get("first_seen_at", now) if prev else now
        entry["last_seen_at"] = now
        entry["is_amended"] = is_amended
        data[key] = entry
        index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return FilingVersion(
            ticker=filing.ticker,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            content_hash=filing.content_hash,
            document_url=filing.document_url,
            is_amended=is_amended,
            changed=changed,
        )

    def get_filing_hash(self, ticker: str, accession_number: str) -> str | None:
        index_path = self._filings_index()
        if not index_path.exists():
            return None
        data = json.loads(index_path.read_text(encoding="utf-8"))
        entry = data.get(f"{ticker}:{accession_number}")
        return entry.get("content_hash") if entry else None

    def create_job(self, job: BackfillJob) -> BackfillJob:
        path = self.root / "backfill" / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        return job

    def update_job(self, job: BackfillJob) -> None:
        path = self.root / "backfill" / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")

    def get_job(self, job_id: str) -> BackfillJob | None:
        path = self.root / "backfill" / f"{job_id}.json"
        if not path.exists():
            return None
        return BackfillJob.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> list[BackfillJob]:
        jobs: list[BackfillJob] = []
        for path in sorted(self.root.glob("backfill/*.json"), reverse=True):
            job = BackfillJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if status and job.status != status:
                continue
            jobs.append(job)
            if len(jobs) >= limit:
                break
        return jobs

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
        path = self.root / "macro" / f"{series_id}.jsonl"
        key = f"{observation_date}:{revision_id}"
        existing: set[str] = set()
        if path.exists():
            for line in path.open(encoding="utf-8"):
                if line.strip():
                    row = json.loads(line)
                    existing.add(f"{row['observation_date']}:{row['revision_id']}")
        if key in existing:
            return False
        row = {
            "series_id": series_id,
            "source": source,
            "observation_date": observation_date,
            "value": value,
            "revision_id": revision_id,
            "published_time": published_time,
            "content_hash": content_hash,
            "metadata": metadata or {},
            "ingested_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return True

    def list_macro_revisions(self, series_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        path = self.root / "macro" / f"{series_id}.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.open(encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
        return rows[-limit:]


# Backward compatibility alias
LocalStorageBackend = LocalPlatformStore
