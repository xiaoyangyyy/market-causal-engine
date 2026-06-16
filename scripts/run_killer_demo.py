#!/usr/bin/env python3
"""Launch killer demo (Streamlit) or export static HTML."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Killer demo launcher")
    parser.add_argument("--static", action="store_true", help="Export static HTML+JSON only")
    parser.add_argument("--case", default="nflx_2022q1_earnings")
    parser.add_argument("--as-of", type=int, default=120)
    args = parser.parse_args()

    if args.static:
        cmd = [sys.executable, str(ROOT / "scripts" / "export_killer_demo.py"), "--case", args.case, f"--as-of={args.as_of}"]
        return subprocess.call(cmd)

    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("Streamlit not installed — exporting static demo instead.")
        print("For interactive UI: pip install -e '.[demo]' && python scripts/run_killer_demo.py")
        cmd = [sys.executable, str(ROOT / "scripts" / "export_killer_demo.py"), "--case", args.case]
        return subprocess.call(cmd)

    app = ROOT / "demo" / "streamlit_app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), "--", f"--case={args.case}"])


if __name__ == "__main__":
    raise SystemExit(main())
