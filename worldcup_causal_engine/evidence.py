"""Text evidence layer: atoms, claim clusters, evidence ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldcup_causal_engine.evidence_types import evidence_type_for_claim
# Emotion → intensity mapping (v0.1)
EMOTION_INTENSITY: dict[str, float] = {
    "anger": 0.9,
    "rage": 1.0,
    "disgust": 0.8,
    "fear": 0.7,
    "sadness": 0.5,
    "surprise": 0.4,
    "joy": 0.2,
    "neutral": 0.3,
    "contempt": 0.75,
}

# Reverse claim pairs for contestation
CONTESTATION_PAIRS: dict[str, str] = {
    "blame_referee": "defend_referee",
    "blame_player": "defend_player",
    "defend_referee": "blame_referee",
    "defend_player": "blame_player",
}

CLAIM_TYPES = {
    "blame_referee": "指责裁判",
    "blame_player": "指责球员",
    "rumor_clip_shared": "传播争议剪辑",
    "official_statement": "官方声明提及",
    "fan_conflict_report": "线下冲突目击",
    "transit_complaint": "交通抱怨",
    "defend_referee": "为裁判辩护",
    "defend_player": "为球员辩护",
}


def time_bucket(minute: int, bucket_size: int = 10) -> str:
    start = (minute // bucket_size) * bucket_size
    end = start + bucket_size
    return f"t{start}_{end}"


@dataclass
class Atom:
    source_id: str
    time: int
    claim_type: str
    target: str
    actor_group: str
    emotion: str
    confidence: float
    raw_text: str
    evidence_type: str = ""
    atom_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.time = int(self.time)
        self.confidence = float(self.confidence)
        if not self.evidence_type:
            self.evidence_type = str(evidence_type_for_claim(self.claim_type))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Atom:
        return cls(
            atom_id=data.get("atom_id", ""),
            source_id=data["source_id"],
            time=int(data["time"]),
            claim_type=data["claim_type"],
            target=data.get("target", ""),
            actor_group=data.get("actor_group", "unknown"),
            emotion=data.get("emotion", "neutral"),
            confidence=float(data.get("confidence", 0.5)),
            raw_text=data.get("raw_text", ""),
            evidence_type=data.get("evidence_type", ""),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "source_id": self.source_id,
            "time": self.time,
            "claim_type": self.claim_type,
            "target": self.target,
            "actor_group": self.actor_group,
            "emotion": self.emotion,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
            "evidence_type": self.evidence_type,
            "metadata": self.metadata,
        }


def cluster_key(atom: Atom, match_id: str = "M12") -> str:
    bucket = time_bucket(atom.time)
    return f"{atom.claim_type}|{atom.actor_group}|{atom.target}|{match_id}|{bucket}"


@dataclass
class ClaimCluster:
    cluster_id: str
    key: str
    claim_type: str
    target: str
    actor_group: str
    time_bucket: str
    support_count: int = 0
    unique_sources: int = 0
    velocity: float = 0.0
    emotion_intensity: float = 0.0
    confidence: float = 0.0
    contestation: float = 0.0
    _source_ids: set[str] = field(default_factory=set, repr=False)
    _dedup_keys: set[str] = field(default_factory=set, repr=False)
    _confidence_sum: float = 0.0
    _confidence_weight: int = 0
    _recent_times: list[int] = field(default_factory=list, repr=False)
    compiled_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "key": self.key,
            "claim_type": self.claim_type,
            "target": self.target,
            "actor_group": self.actor_group,
            "time_bucket": self.time_bucket,
            "support_count": self.support_count,
            "unique_sources": self.unique_sources,
            "velocity": round(self.velocity, 4),
            "emotion_intensity": round(self.emotion_intensity, 4),
            "confidence": round(self.confidence, 4),
            "contestation": round(self.contestation, 4),
            "compiled_to": self.compiled_to,
        }


def emotion_to_intensity(emotion: str) -> float:
    return EMOTION_INTENSITY.get(emotion.lower(), 0.3)


def update_cluster(cluster: ClaimCluster, atom: Atom, window_size: int = 10) -> None:
    cluster.support_count += 1
    cluster._source_ids.add(atom.source_id)
    cluster.unique_sources = len(cluster._source_ids)

    cluster._confidence_sum += atom.confidence
    cluster._confidence_weight += 1
    cluster.confidence = cluster._confidence_sum / cluster._confidence_weight

    ema_alpha = 0.3
    new_intensity = emotion_to_intensity(atom.emotion)
    if cluster.support_count == 1:
        cluster.emotion_intensity = new_intensity
    else:
        cluster.emotion_intensity = (
            ema_alpha * new_intensity + (1 - ema_alpha) * cluster.emotion_intensity
        )

    cluster._recent_times.append(atom.time)
    cluster._recent_times = cluster._recent_times[-window_size:]
    cluster.velocity = len(cluster._recent_times) / window_size


class EvidenceLedger:
    def __init__(
        self,
        ledger_id: str = "default",
        match_id: str = "M12",
        min_confidence: float = 0.3,
        velocity_window: int = 10,
    ):
        self.ledger_id = ledger_id
        self.match_id = match_id
        self.min_confidence = min_confidence
        self.velocity_window = velocity_window
        self.atoms: list[Atom] = []
        self.clusters: dict[str, ClaimCluster] = {}
        self.compiled_cluster_ids: set[str] = set()
        self._cluster_counter = 0
        self._key_to_id: dict[str, str] = {}
        self._dedup_global: set[str] = set()

    def _next_cluster_id(self) -> str:
        self._cluster_counter += 1
        return f"C{self._cluster_counter}"

    def _next_atom_id(self) -> str:
        return f"A{len(self.atoms) + 1}"

    def _dedup_key(self, atom: Atom) -> str:
        bucket = time_bucket(atom.time)
        return f"{atom.source_id}|{atom.claim_type}|{bucket}|{atom.raw_text}"

    def ingest(self, atom: Atom) -> str | None:
        if not atom.atom_id:
            atom.atom_id = self._next_atom_id()
        self.atoms.append(atom)

        dedup = self._dedup_key(atom)
        if dedup in self._dedup_global:
            return None
        self._dedup_global.add(dedup)

        if atom.confidence < self.min_confidence:
            return None

        key = cluster_key(atom, self.match_id)
        if key not in self._key_to_id:
            cid = self._next_cluster_id()
            self._key_to_id[key] = cid
            parts = key.split("|")
            self.clusters[cid] = ClaimCluster(
                cluster_id=cid,
                key=key,
                claim_type=parts[0],
                target=parts[2],
                actor_group=parts[1],
                time_bucket=parts[4],
            )

        cluster_id = self._key_to_id[key]
        cluster = self.clusters[cluster_id]
        cluster._dedup_keys.add(dedup)
        update_cluster(cluster, atom, self.velocity_window)

        self._update_contestation(atom)
        return cluster_id

    def _update_contestation(self, atom: Atom) -> None:
        reverse = CONTESTATION_PAIRS.get(atom.claim_type)
        if not reverse:
            return

        bucket = time_bucket(atom.time)
        for cluster in self.clusters.values():
            if (
                cluster.claim_type == reverse
                and cluster.target == atom.target
                and cluster.time_bucket == bucket
            ):
                cluster.contestation = min(1.0, cluster.contestation + 0.15)

        if atom.claim_type in ("defend_referee", "defend_player"):
            for cluster in self.clusters.values():
                if (
                    cluster.claim_type == CONTESTATION_PAIRS.get(atom.claim_type, "")
                    and cluster.target == atom.target
                    and cluster.time_bucket == bucket
                ):
                    cluster.contestation = min(1.0, cluster.contestation + 0.05)

    def get_cluster(self, cluster_id: str) -> ClaimCluster | None:
        return self.clusters.get(cluster_id)

    def mark_compiled(self, cluster_id: str, emit_kind: str) -> None:
        self.compiled_cluster_ids.add(cluster_id)
        if cluster_id in self.clusters:
            self.clusters[cluster_id].compiled_to = emit_kind

    def summary(self) -> dict[str, Any]:
        top = sorted(
            self.clusters.values(),
            key=lambda c: c.support_count,
            reverse=True,
        )[:5]
        return {
            "ledger_id": self.ledger_id,
            "match_id": self.match_id,
            "total_atoms": len(self.atoms),
            "total_clusters": len(self.clusters),
            "compiled_clusters": len(self.compiled_cluster_ids),
            "top_clusters": [c.to_dict() for c in top],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "atoms": [a.to_dict() for a in self.atoms],
            "clusters": {cid: c.to_dict() for cid, c in self.clusters.items()},
            "compiled_cluster_ids": sorted(self.compiled_cluster_ids),
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> EvidenceLedger:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        ledger = cls(
            ledger_id=data.get("ledger_id", "loaded"),
            match_id=data.get("match_id", "M12"),
        )
        for atom_data in data.get("atoms", []):
            ledger.atoms.append(Atom.from_dict(atom_data))
        for cid, cdata in data.get("clusters", {}).items():
            cluster = ClaimCluster(
                cluster_id=cdata["cluster_id"],
                key=cdata["key"],
                claim_type=cdata["claim_type"],
                target=cdata["target"],
                actor_group=cdata["actor_group"],
                time_bucket=cdata["time_bucket"],
                support_count=cdata["support_count"],
                unique_sources=cdata["unique_sources"],
                velocity=cdata["velocity"],
                emotion_intensity=cdata["emotion_intensity"],
                confidence=cdata["confidence"],
                contestation=cdata["contestation"],
                compiled_to=cdata.get("compiled_to"),
            )
            ledger.clusters[cid] = cluster
            ledger._key_to_id[cluster.key] = cid
        ledger.compiled_cluster_ids = set(data.get("compiled_cluster_ids", []))
        ledger._cluster_counter = len(ledger.clusters)
        return ledger


def load_atoms_from_jsonl(path: str | Path) -> list[Atom]:
    atoms: list[Atom] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            atoms.append(Atom.from_dict(json.loads(line)))
    return sorted(atoms, key=lambda a: (a.time, a.atom_id))
