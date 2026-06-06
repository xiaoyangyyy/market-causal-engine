"""Normalize raw source data into Observation JSONL.

MVP ships only a helper that validates and writes already-structured records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from worldcup_causal_engine.calibration.observations import Observation


def normalize_to_observations_jsonl(
    records: Iterable[dict[str, Any]],
    *,
    out_path: str | Path,
) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for r in records:
        o = Observation.from_dict(r)
        lines.append(json.dumps(o.to_dict(), ensure_ascii=False))

    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return str(out)

