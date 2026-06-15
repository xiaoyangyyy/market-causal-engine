"""Postgres/Timescale platform store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from market_causal_engine.platform.db import apply_migrations, migration_sql
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope
from market_causal_engine.platform.provenance import RunManifest
from market_causal_engine.platform.registry import BackfillJob, FilingVersion
from market_causal_engine.platform.storage.base import PlatformStore


class PostgresPlatformStore(PlatformStore):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg

            self._conn = psycopg.connect(self.database_url)
        return self._conn

    def ensure_schema(self) -> None:
        apply_migrations(self._get_conn())

    def save_records(self, snapshot_id: str, records: list[PITRecord]) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_snapshots (snapshot_id, record_count)
                VALUES (%s, 0)
                ON CONFLICT (snapshot_id) DO NOTHING
                """,
                (snapshot_id,),
            )
            stored = 0
            for rec in records:
                cur.execute(
                    """
                    INSERT INTO pit_records (
                        record_id, snapshot_id, source_kind, source_id, payload,
                        observed_time, published_time, ingested_time, revision_id,
                        content_hash, schema_version, metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (snapshot_id, source_id, revision_id) DO NOTHING
                    """,
                    (
                        rec.record_id,
                        snapshot_id,
                        rec.source_kind.value,
                        rec.source_id,
                        json.dumps(rec.payload),
                        rec.temporal.observed_time,
                        rec.temporal.published_time,
                        rec.temporal.ingested_time,
                        rec.temporal.revision_id,
                        rec.content_hash,
                        rec.schema_version,
                        json.dumps(rec.metadata),
                    ),
                )
                if cur.rowcount:
                    stored += 1
            cur.execute(
                """
                UPDATE data_snapshots
                SET record_count = (SELECT COUNT(*) FROM pit_records WHERE snapshot_id = %s),
                    meta = jsonb_set(COALESCE(meta, '{}'::jsonb), '{updated_at}', to_jsonb(NOW()::text))
                WHERE snapshot_id = %s
                """,
                (snapshot_id, snapshot_id),
            )
        conn.commit()
        return stored

    def list_records(
        self,
        *,
        snapshot_id: str | None = None,
        source_kind: SourceKind | None = None,
        limit: int = 100,
    ) -> list[PITRecord]:
        conn = self._get_conn()
        sid = snapshot_id or self.latest_snapshot_id()
        if not sid:
            return []
        query = """
            SELECT record_id, source_kind, source_id, payload, observed_time,
                   published_time, ingested_time, revision_id, content_hash,
                   schema_version, metadata
            FROM pit_records WHERE snapshot_id = %s
        """
        params: list[Any] = [sid]
        if source_kind:
            query += " AND source_kind = %s"
            params.append(source_kind.value)
        query += " ORDER BY published_time DESC LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        out: list[PITRecord] = []
        for row in rows:
            payload = row[3] if isinstance(row[3], dict) else json.loads(row[3])
            metadata = row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}")
            out.append(
                PITRecord(
                    record_id=row[0],
                    source_kind=SourceKind(row[1]),
                    source_id=row[2],
                    payload=payload,
                    temporal=TemporalEnvelope(
                        observed_time=row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
                        published_time=row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
                        ingested_time=row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
                        revision_id=str(row[7]),
                    ),
                    schema_version=str(row[9]),
                    content_hash=str(row[8]),
                    metadata=metadata,
                )
            )
        return out

    def save_manifest(self, manifest: RunManifest) -> None:
        conn = self._get_conn()
        data = manifest.to_dict()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO run_manifests (
                    run_id, data_snapshot_id, model_version, ruleset_version,
                    source_hashes, as_of_time, created_at, stages, status, error
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO UPDATE SET
                    stages = EXCLUDED.stages,
                    status = EXCLUDED.status,
                    error = EXCLUDED.error,
                    source_hashes = EXCLUDED.source_hashes
                """,
                (
                    data["run_id"],
                    data.get("data_snapshot_id"),
                    data.get("model_version"),
                    data.get("ruleset_version"),
                    json.dumps(data.get("source_hashes", {})),
                    data.get("as_of_time"),
                    data.get("created_at"),
                    json.dumps(data.get("stages", [])),
                    data.get("status"),
                    data.get("error"),
                ),
            )
        conn.commit()

    def load_manifest(self, run_id: str) -> RunManifest | None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, data_snapshot_id, model_version, ruleset_version,
                       source_hashes, as_of_time, created_at, stages, status, error
                FROM run_manifests WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return RunManifest.from_dict(
            {
                "run_id": row[0],
                "data_snapshot_id": row[1],
                "model_version": row[2],
                "ruleset_version": row[3],
                "source_hashes": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
                "as_of_time": row[5].isoformat() if hasattr(row[5], "isoformat") else row[5],
                "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else row[6],
                "stages": row[7] if isinstance(row[7], list) else json.loads(row[7] or "[]"),
                "status": row[8],
                "error": row[9],
            }
        )

    def latest_snapshot_id(self) -> str | None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT snapshot_id FROM data_snapshots ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
        return row[0] if row else None

    def freshness_report(self) -> dict[str, Any]:
        conn = self._get_conn()
        snap_id = self.latest_snapshot_id()
        if not snap_id:
            return {"backend": "postgres", "latest_snapshot_id": None, "sources": {}, "stale": True}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_kind, MAX(published_time)::text, COUNT(*)
                FROM pit_records WHERE snapshot_id = %s
                GROUP BY source_kind
                """,
                (snap_id,),
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT meta->>'updated_at', record_count FROM data_snapshots WHERE snapshot_id = %s",
                (snap_id,),
            )
            meta_row = cur.fetchone()
        sources = {r[0]: r[1] for r in rows}
        return {
            "backend": "postgres",
            "latest_snapshot_id": snap_id,
            "updated_at": meta_row[0] if meta_row else None,
            "record_count": meta_row[1] if meta_row else 0,
            "sources": sources,
            "stale": meta_row[0] is None if meta_row else True,
        }

    def upsert_filing(self, filing: FilingVersion) -> FilingVersion:
        conn = self._get_conn()
        prev_hash = self.get_filing_hash(filing.ticker, filing.accession_number)
        changed = prev_hash is None or prev_hash != filing.content_hash
        is_amended = prev_hash is not None and changed
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO filing_versions (
                    ticker, accession_number, form_type, filing_date,
                    content_hash, document_url, is_amended, last_seen_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (ticker, accession_number) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    is_amended = CASE
                        WHEN filing_versions.content_hash <> EXCLUDED.content_hash THEN TRUE
                        ELSE filing_versions.is_amended
                    END,
                    last_seen_at = NOW(),
                    document_url = EXCLUDED.document_url
                """,
                (
                    filing.ticker,
                    filing.accession_number,
                    filing.form_type,
                    filing.filing_date,
                    filing.content_hash,
                    filing.document_url,
                    is_amended,
                ),
            )
        conn.commit()
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
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM filing_versions WHERE ticker = %s AND accession_number = %s",
                (ticker, accession_number),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def create_job(self, job: BackfillJob) -> BackfillJob:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO backfill_jobs (
                    job_id, job_type, status, cursor, total, completed, failed, config, started_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                """,
                (
                    job.job_id,
                    job.job_type,
                    job.status,
                    json.dumps(job.cursor or {}),
                    job.total,
                    job.completed,
                    job.failed,
                    json.dumps(job.config or {}),
                ),
            )
        conn.commit()
        return job

    def update_job(self, job: BackfillJob) -> None:
        conn = self._get_conn()
        finished = job.status in ("succeeded", "failed", "cancelled")
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE backfill_jobs SET
                    status = %s, cursor = %s, total = %s, completed = %s,
                    failed = %s, error = %s, config = %s, updated_at = NOW(),
                    finished_at = CASE WHEN %s THEN NOW() ELSE finished_at END
                WHERE job_id = %s
                """,
                (
                    job.status,
                    json.dumps(job.cursor or {}),
                    job.total,
                    job.completed,
                    job.failed,
                    job.error,
                    json.dumps(job.config or {}),
                    finished,
                    job.job_id,
                ),
            )
        conn.commit()

    def get_job(self, job_id: str) -> BackfillJob | None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id, job_type, status, cursor, total, completed, failed, error, config
                FROM backfill_jobs WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return BackfillJob.from_dict(
            {
                "job_id": row[0],
                "job_type": row[1],
                "status": row[2],
                "cursor": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
                "total": row[4],
                "completed": row[5],
                "failed": row[6],
                "error": row[7],
                "config": row[8] if isinstance(row[8], dict) else json.loads(row[8] or "{}"),
            }
        )

    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> list[BackfillJob]:
        conn = self._get_conn()
        query = """
            SELECT job_id, job_type, status, cursor, total, completed, failed, error, config
            FROM backfill_jobs
        """
        params: list[Any] = []
        if status:
            query += " WHERE status = %s"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        jobs: list[BackfillJob] = []
        for row in rows:
            jobs.append(
                BackfillJob.from_dict(
                    {
                        "job_id": row[0],
                        "job_type": row[1],
                        "status": row[2],
                        "cursor": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
                        "total": row[4],
                        "completed": row[5],
                        "failed": row[6],
                        "error": row[7],
                        "config": row[8] if isinstance(row[8], dict) else json.loads(row[8] or "{}"),
                    }
                )
            )
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
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO macro_series_points (
                    series_id, source, observation_date, value, revision_id,
                    published_time, content_hash, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (series_id, observation_date, revision_id) DO NOTHING
                """,
                (
                    series_id,
                    source,
                    observation_date,
                    value,
                    revision_id,
                    published_time,
                    content_hash,
                    json.dumps(metadata or {}),
                ),
            )
            inserted = cur.rowcount > 0
        conn.commit()
        return inserted

    def list_macro_revisions(self, series_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT observation_date, value, revision_id, published_time, content_hash, source
                FROM macro_series_points
                WHERE series_id = %s
                ORDER BY observation_date DESC, revision_id DESC
                LIMIT %s
                """,
                (series_id, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "observation_date": str(r[0]),
                "value": float(r[1]) if r[1] is not None else None,
                "revision_id": r[2],
                "published_time": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
                "content_hash": r[4],
                "source": r[5],
            }
            for r in rows
        ]

    @staticmethod
    def migration_sql() -> str:
        return migration_sql()
