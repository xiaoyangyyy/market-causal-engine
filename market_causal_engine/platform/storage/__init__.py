"""Storage backends for PIT records and run manifests."""

from market_causal_engine.platform.storage.base import PlatformStore, StorageBackend
from market_causal_engine.platform.storage.factory import get_platform_store
from market_causal_engine.platform.storage.local import LocalPlatformStore, LocalStorageBackend
from market_causal_engine.platform.storage.postgres import PostgresPlatformStore

__all__ = [
    "PlatformStore",
    "StorageBackend",
    "LocalPlatformStore",
    "LocalStorageBackend",
    "PostgresPlatformStore",
    "get_platform_store",
]
