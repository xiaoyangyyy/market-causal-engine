"""Downloader interface for post-hoc data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class DownloadResult:
    source: str
    files: list[str]
    meta: dict[str, Any] = field(default_factory=dict)


class Downloader(Protocol):
    """Fetch raw data files into a local directory."""

    source: str

    def fetch(self, *, out_dir: str | Path, query: dict[str, Any]) -> DownloadResult:  # pragma: no cover
        raise NotImplementedError

