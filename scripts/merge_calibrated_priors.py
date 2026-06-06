#!/usr/bin/env python3
"""Regenerate data/priors/mechanisms_v0.2_calibrated.json from calibration reports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_causal_engine.calibration.merge_priors import write_calibrated_priors


def main() -> int:
    path = write_calibrated_priors(
        report_dir=ROOT / "results" / "calibration",
    )
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
