"""Evidence layer: atoms and claim clusters for market events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MarketAtom:
    atom_id: str
    text: str
    source: str
    time: int
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    published_at: int | None = None

    def effective_time(self) -> int:
        """Minute on case-study timeline when this evidence becomes admissible."""
        if self.published_at is not None:
            return int(self.published_at)
        return int(self.time)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "atom_id": self.atom_id,
            "text": self.text,
            "source": self.source,
            "time": self.time,
            "tags": self.tags,
            "metadata": self.metadata,
        }
        if self.published_at is not None:
            out["published_at"] = self.published_at
        return out


@dataclass
class ClaimCluster:
    cluster_id: str
    atoms: list[MarketAtom]
    time: int
    topic: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "time": self.time,
            "topic": self.topic,
            "atoms": [a.to_dict() for a in self.atoms],
        }


def load_atoms(path: str | Path) -> list[MarketAtom]:
    atoms: list[MarketAtom] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            atoms.append(
                MarketAtom(
                    atom_id=raw["atom_id"],
                    text=raw["text"],
                    source=raw.get("source", "unknown"),
                    time=int(raw["time"]),
                    tags=list(raw.get("tags", [])),
                    metadata=dict(raw.get("metadata", {})),
                    published_at=int(raw["published_at"]) if "published_at" in raw else None,
                )
            )
    return atoms


def save_atoms(atoms: list[MarketAtom], path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for atom in atoms:
            f.write(json.dumps(atom.to_dict(), ensure_ascii=False) + "\n")
