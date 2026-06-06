"""Download adapters for post-hoc observations (Phase 8).

This package defines interfaces and normalization helpers.
Concrete implementations should be added per data source.
"""

from worldcup_causal_engine.calibration.downloaders.base import Downloader, DownloadResult
from worldcup_causal_engine.calibration.downloaders.normalize import normalize_to_observations_jsonl

__all__ = ["Downloader", "DownloadResult", "normalize_to_observations_jsonl"]

