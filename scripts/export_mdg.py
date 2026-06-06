#!/usr/bin/env python3
"""Export MDG Mermaid diagrams for all scenarios to paper/figures/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worldcup_causal_engine.constants import SCENARIO_FILES
from worldcup_causal_engine.mdg.builder import build_event_mdg_from_result
from worldcup_causal_engine.mdg.export import export_mermaid_file
from worldcup_causal_engine.scenarios import run_scenario


def main() -> int:
    out_dir = ROOT / "paper" / "figures" / "mdg"
    out_dir.mkdir(parents=True, exist_ok=True)

    for short, filename in SCENARIO_FILES.items():
        path = ROOT / "data" / "scenarios" / filename
        result = run_scenario(path, world_id="W0", until=120)
        mdg = build_event_mdg_from_result(result)
        out = out_dir / f"{short}_W0.mmd"
        export_mermaid_file(mdg, out, title=f"{short} W0")
        print(f"Wrote {out}")

    index = out_dir / "README.txt"
    index.write_text(
        "Event-level MDG Mermaid files. Paste into https://mermaid.live or VS Code Mermaid preview.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
