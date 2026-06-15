"""Paths and manifest I/O for catalog event artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.models import BENCHMARK_DIR

CATALOG_ROOT = BENCHMARK_DIR / "catalog"


def catalog_root() -> Path:
    return CATALOG_ROOT


def catalog_event_dir(event_id: str) -> Path:
    return CATALOG_ROOT / event_id


def atoms_path(event_id: str) -> Path:
    return catalog_event_dir(event_id) / "atoms.jsonl"


def manifest_path(event_id: str) -> Path:
    return catalog_event_dir(event_id) / "manifest.json"


def sec_text_path(event_id: str) -> Path:
    return catalog_event_dir(event_id) / "sec_8k.txt"


def causal_claims_path(event_id: str) -> Path:
    return catalog_event_dir(event_id) / "causal_claims.json"


def load_manifest(event_id: str) -> dict[str, Any]:
    path = manifest_path(event_id)
    if not path.exists():
        raise FileNotFoundError(f"Catalog manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(event_id: str, data: dict[str, Any]) -> Path:
    path = manifest_path(event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
