-- P1: Point-in-time storage schema (Postgres / TimescaleDB compatible)
-- Apply: psql $DATABASE_URL -f market_causal_engine/platform/db/migrations/001_pit_schema.sql

CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    record_count INT NOT NULL DEFAULT 0,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS pit_records (
    record_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    observed_time TIMESTAMPTZ NOT NULL,
    published_time TIMESTAMPTZ NOT NULL,
    ingested_time TIMESTAMPTZ NOT NULL,
    revision_id TEXT NOT NULL DEFAULT 'initial',
    content_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'pit_v1',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (snapshot_id, source_id, revision_id)
);

CREATE INDEX IF NOT EXISTS idx_pit_published ON pit_records(published_time DESC);
CREATE INDEX IF NOT EXISTS idx_pit_source_kind ON pit_records(source_kind);
CREATE INDEX IF NOT EXISTS idx_pit_ingested ON pit_records(ingested_time DESC);

-- EDGAR filing version registry (diff detection)
CREATE TABLE IF NOT EXISTS filing_versions (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filing_date DATE NOT NULL,
    content_hash TEXT NOT NULL,
    document_url TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_amended BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (ticker, accession_number)
);

CREATE INDEX IF NOT EXISTS idx_filing_ticker_date ON filing_versions(ticker, filing_date DESC);

-- Pipeline run manifests
CREATE TABLE IF NOT EXISTS run_manifests (
    run_id TEXT PRIMARY KEY,
    data_snapshot_id TEXT,
    model_version TEXT,
    ruleset_version TEXT,
    source_hashes JSONB NOT NULL DEFAULT '{}'::jsonb,
    as_of_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stages JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);

-- Backfill job progress (resumable)
CREATE TABLE IF NOT EXISTS backfill_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    cursor JSONB NOT NULL DEFAULT '{}'::jsonb,
    total INT NOT NULL DEFAULT 0,
    completed INT NOT NULL DEFAULT 0,
    failed INT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_backfill_status ON backfill_jobs(status);

-- FRED/BLS macro series revisions
CREATE TABLE IF NOT EXISTS macro_series_points (
    id BIGSERIAL PRIMARY KEY,
    series_id TEXT NOT NULL,
    source TEXT NOT NULL,
    observation_date DATE NOT NULL,
    value NUMERIC,
    revision_id TEXT NOT NULL,
    vintage_date DATE,
    published_time TIMESTAMPTZ NOT NULL,
    ingested_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (series_id, observation_date, revision_id)
);

CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_series_points(series_id, observation_date DESC);

-- Optional Timescale hypertable (no-op if extension missing)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('pit_records', 'ingested_time', if_not_exists => TRUE, migrate_data => TRUE);
        PERFORM create_hypertable('macro_series_points', 'ingested_time', if_not_exists => TRUE, migrate_data => TRUE);
    END IF;
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;
