"""Event-level Mechanism Dependency Graph (MDG).

Nodes are event kinds (e.g. rumor_amplified). Edges represent dependency signals:
- contract_emits / spec_emits: declared next-event emission
- trace_successor: observed adjacency in executed trace
- flag_wait: inferred producer(kind_that_sets_flag) -> consumer(kind_waits_flag)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


EdgeType = Literal["contract_emits", "spec_emits", "trace_successor", "flag_wait"]


@dataclass(frozen=True)
class EdgeEvidence:
    edge_type: EdgeType
    weight: float = 1.0
    count: int = 0
    detail: str = ""
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_type": self.edge_type,
            "weight": round(float(self.weight), 6),
            "count": int(self.count),
            "detail": self.detail,
            "sources": list(self.sources),
        }


@dataclass
class MDGNode:
    kind: str
    waits: list[str] = field(default_factory=list)
    resources: dict[str, float] = field(default_factory=dict)
    contract_version: str | None = None
    spec_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.waits:
            out["waits"] = list(self.waits)
        if self.resources:
            out["resources"] = dict(self.resources)
        if self.contract_version:
            out["contract_version"] = self.contract_version
        if self.spec_version:
            out["spec_version"] = self.spec_version
        return out


@dataclass
class MDGEdge:
    src: str
    dst: str
    evidences: list[EdgeEvidence] = field(default_factory=list)

    def key(self) -> tuple[str, str]:
        return (self.src, self.dst)

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "evidences": [e.to_dict() for e in self.evidences],
        }


@dataclass
class EventMDG:
    """Event-kind dependency graph with merged evidences."""

    nodes: dict[str, MDGNode] = field(default_factory=dict)
    edges: dict[tuple[str, str], MDGEdge] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def upsert_node(self, node: MDGNode) -> None:
        if node.kind not in self.nodes:
            self.nodes[node.kind] = node
            return
        existing = self.nodes[node.kind]
        existing.waits = sorted(set(existing.waits).union(node.waits))
        existing.resources.update(node.resources)
        existing.contract_version = existing.contract_version or node.contract_version
        existing.spec_version = existing.spec_version or node.spec_version

    def add_edge(self, src: str, dst: str, evidence: EdgeEvidence) -> None:
        if src == dst:
            return
        k = (src, dst)
        if k not in self.edges:
            self.edges[k] = MDGEdge(src=src, dst=dst, evidences=[evidence])
            return
        self.edges[k].evidences.append(evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": dict(self.meta),
            "nodes": [n.to_dict() for n in sorted(self.nodes.values(), key=lambda x: x.kind)],
            "edges": [e.to_dict() for e in sorted(self.edges.values(), key=lambda x: (x.src, x.dst))],
        }

