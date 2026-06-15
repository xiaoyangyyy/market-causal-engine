"""Database connection and migration helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_MIGRATION = Path(__file__).resolve().parent / "migrations" / "001_pit_schema.sql"


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("MARKET_CAUSAL_DATABASE_URL")


def migration_sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def apply_migrations(conn: Any) -> None:
    """Execute migration SQL on an open psycopg connection."""
    sql = migration_sql()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def connect():
    """Return psycopg connection or raise ImportError/ConnectionError."""
    url = database_url()
    if not url:
        raise ConnectionError("DATABASE_URL not set")
    try:
        import psycopg
    except ImportError as exc:
        raise ImportError("Install platform extras: pip install -e '.[platform]'") from exc
    return psycopg.connect(url)
