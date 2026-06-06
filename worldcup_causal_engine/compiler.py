"""Compile claim clusters into typed kernel events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldcup_causal_engine.evidence import ClaimCluster, EvidenceLedger
from worldcup_causal_engine.evidence_types import evidence_type_for_claim


@dataclass
class CompiledEvent:
    kind: str
    time: int
    priority: int
    payload: dict[str, Any]
    cause: list[str] = field(default_factory=list)
    cluster_id: str = ""
    evidence_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "time": self.time,
            "priority": self.priority,
            "payload": self.payload,
            "cause": self.cause,
            "cluster_id": self.cluster_id,
            "evidence_summary": self.evidence_summary,
        }


@dataclass
class CompileRule:
    claim_type: str
    emit_kind: str
    thresholds: dict[str, float]
    payload_mapping: dict[str, str] = field(default_factory=dict)
    priority: int = 2
    max_contestation: float = 0.85
    compile: bool = True

    @classmethod
    def from_dict(cls, claim_type: str, data: dict[str, Any]) -> CompileRule:
        return cls(
            claim_type=claim_type,
            emit_kind=data.get("emit_kind", ""),
            thresholds={k: float(v) for k, v in data.get("thresholds", {}).items()},
            payload_mapping=dict(data.get("payload_mapping", {})),
            priority=int(data.get("priority", 2)),
            max_contestation=float(data.get("max_contestation", 0.85)),
            compile=bool(data.get("compile", True)),
        )


class CompilerRules:
    def __init__(self, rules: dict[str, CompileRule] | None = None):
        self.rules = rules or {}

    @classmethod
    def load(cls, path: str | Path) -> CompilerRules:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        rules = {
            claim_type: CompileRule.from_dict(claim_type, spec)
            for claim_type, spec in raw.items()
        }
        return cls(rules)

    def get(self, claim_type: str) -> CompileRule | None:
        return self.rules.get(claim_type)


def should_compile(cluster: ClaimCluster, rule: CompileRule) -> bool:
    if not rule.compile or not rule.emit_kind:
        return False
    if cluster.contestation > rule.max_contestation:
        return False
    for metric, threshold in rule.thresholds.items():
        value = getattr(cluster, metric, None)
        if value is None:
            return False
        if float(value) < threshold:
            return False
    return True


def _resolve_payload_value(cluster: ClaimCluster, mapping_value: str) -> Any:
    if mapping_value in ("velocity", "confidence", "emotion_intensity", "support_count"):
        return round(getattr(cluster, mapping_value), 4)
    return mapping_value


def compile_cluster(cluster: ClaimCluster, rule: CompileRule) -> CompiledEvent:
    payload: dict[str, Any] = {}
    for field_name, source in rule.payload_mapping.items():
        payload[field_name] = _resolve_payload_value(cluster, source)

    if "severity" not in payload:
        intensity = payload.get("intensity", cluster.emotion_intensity)
        if isinstance(intensity, (int, float)):
            payload["severity"] = min(1.0, max(0.3, float(intensity)))
        else:
            payload["severity"] = min(1.0, max(0.3, cluster.confidence))

    bucket_parts = cluster.time_bucket.replace("t", "").split("_")
    compile_time = int(bucket_parts[1]) if len(bucket_parts) == 2 else int(bucket_parts[0])

    return CompiledEvent(
        kind=rule.emit_kind,
        time=compile_time,
        priority=rule.priority,
        payload=payload,
        cause=[f"claim_cluster:{cluster.cluster_id}"],
        cluster_id=cluster.cluster_id,
        evidence_summary={
            "cluster_id": cluster.cluster_id,
            "claim_type": cluster.claim_type,
            "evidence_type": str(evidence_type_for_claim(cluster.claim_type)),
            "confidence": round(cluster.confidence, 4),
            "support_count": int(cluster.support_count),
            "unique_sources": int(cluster.unique_sources),
        },
    )


class Compiler:
    def __init__(self, rules: CompilerRules):
        self.rules = rules

    def try_compile(self, ledger: EvidenceLedger) -> list[CompiledEvent]:
        compiled: list[CompiledEvent] = []
        for cluster_id, cluster in ledger.clusters.items():
            if cluster_id in ledger.compiled_cluster_ids:
                continue
            rule = self.rules.get(cluster.claim_type)
            if rule is None or not should_compile(cluster, rule):
                continue
            event = compile_cluster(cluster, rule)
            ledger.mark_compiled(cluster_id, event.kind)
            compiled.append(event)
        return compiled


def load_default_rules() -> CompilerRules:
    root = Path(__file__).resolve().parent.parent
    return CompilerRules.load(root / "data" / "compiler_rules" / "v0.1.json")
