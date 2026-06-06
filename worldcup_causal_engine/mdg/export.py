"""MDG export helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from worldcup_causal_engine.mdg.graph import EventMDG


def _safe_id(kind: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", kind)


def export_mermaid(mdg: EventMDG, *, title: str = "Event MDG") -> str:
    """Mermaid flowchart (event-level)."""
    lines = ["flowchart LR", f"    %% {title}"]
    node_ids: dict[str, str] = {}
    for kind in sorted(mdg.nodes.keys()):
        nid = _safe_id(kind)
        node_ids[kind] = nid
        waits = mdg.nodes[kind].waits
        label = kind.replace("_", " ")
        if waits:
            label += f"\\nwaits:{','.join(waits[:2])}"
        lines.append(f'    {nid}["{label}"]')

    seen_edges: set[tuple[str, str]] = set()
    for (src, dst), edge in sorted(mdg.edges.items()):
        if (src, dst) in seen_edges:
            continue
        seen_edges.add((src, dst))
        types = sorted({e.edge_type for e in edge.evidences})
        tag = types[0] if len(types) == 1 else "mixed"
        lines.append(f"    {node_ids[src]} -->|{tag}| {node_ids[dst]}")

    return "\n".join(lines) + "\n"


def export_mermaid_file(mdg: EventMDG, path: str | Path, *, title: str = "Event MDG") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(export_mermaid(mdg, title=title), encoding="utf-8")
    return str(p)


def export_json(mdg: EventMDG, path: str | Path) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = mdg.to_dict()
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)

