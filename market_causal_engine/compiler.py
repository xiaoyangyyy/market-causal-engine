"""Compiler: map evidence atoms to typed market causal events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from market_causal_engine.evidence import ClaimCluster, MarketAtom


@dataclass(frozen=True)
class CompilerRule:
    rule_id: str
    match_tags: tuple[str, ...]
    match_keywords: tuple[str, ...]
    event_kind: str
    default_severity: float
    payload_keys: tuple[str, ...] = ()


@dataclass
class CompiledEvent:
    event_kind: str
    time: int
    severity: float
    payload: dict[str, Any]
    source_cluster_id: str
    rule_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_kind": self.event_kind,
            "time": self.time,
            "severity": self.severity,
            "payload": self.payload,
            "source_cluster_id": self.source_cluster_id,
            "rule_id": self.rule_id,
        }


def load_compiler_rules(path: str | Path) -> list[CompilerRule]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rules: list[CompilerRule] = []
    for item in raw.get("rules", []):
        rules.append(
            CompilerRule(
                rule_id=item["rule_id"],
                match_tags=tuple(item.get("match_tags", [])),
                match_keywords=tuple(item.get("match_keywords", [])),
                event_kind=item["event_kind"],
                default_severity=float(item.get("default_severity", 0.7)),
                payload_keys=tuple(item.get("payload_keys", [])),
            )
        )
    return rules


class MarketCompiler:
    """Text evidence cannot change market state — only compiled events can."""

    def __init__(self, rules: list[CompilerRule]):
        self.rules = rules

    def compile_atom(self, atom: MarketAtom) -> CompiledEvent | None:
        text_lower = atom.text.lower()
        for rule in self.rules:
            tag_match = not rule.match_tags or any(t in atom.tags for t in rule.match_tags)
            kw_match = not rule.match_keywords or any(kw in text_lower for kw in rule.match_keywords)
            if tag_match and kw_match:
                payload = {
                    k: v
                    for k, v in atom.metadata.items()
                    if k not in ("severity", "source_class", "available_from", "uses_future_price")
                }
                event_time = atom.effective_time()
                return CompiledEvent(
                    event_kind=rule.event_kind,
                    time=event_time,
                    severity=float(atom.metadata.get("severity", rule.default_severity)),
                    payload=payload,
                    source_cluster_id=atom.atom_id,
                    rule_id=rule.rule_id,
                )
        return None

    def compile_cluster(self, cluster: ClaimCluster) -> list[CompiledEvent]:
        events: list[CompiledEvent] = []
        for atom in cluster.atoms:
            compiled = self.compile_atom(atom)
            if compiled:
                events.append(compiled)
        return events
