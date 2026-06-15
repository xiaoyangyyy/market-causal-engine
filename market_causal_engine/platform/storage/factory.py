"""Resolve platform storage backend from environment."""

from __future__ import annotations

import os
from pathlib import Path

from market_causal_engine.platform.storage.base import PlatformStore
from market_causal_engine.platform.storage.local import LocalPlatformStore


def get_platform_store(*, store_root: Path | None = None) -> PlatformStore:
    url = os.environ.get("DATABASE_URL") or os.environ.get("MARKET_CAUSAL_DATABASE_URL")
    if url:
        from market_causal_engine.platform.storage.postgres import PostgresPlatformStore

        store = PostgresPlatformStore(url)
        store.ensure_schema()
        return store
    return LocalPlatformStore(store_root)


def default_watchlist_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "platform" / "watchlist.json"
