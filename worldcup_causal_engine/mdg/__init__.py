"""Mechanism Dependency Graph (event-level) utilities."""

from worldcup_causal_engine.mdg.builder import build_event_mdg_from_result
from worldcup_causal_engine.mdg.graph import EdgeEvidence, EventMDG, MDGEdge, MDGNode
from worldcup_causal_engine.mdg.queries import downstream, explain_why_not, upstream

__all__ = [
    "EventMDG",
    "MDGNode",
    "MDGEdge",
    "EdgeEvidence",
    "build_event_mdg_from_result",
    "downstream",
    "upstream",
    "explain_why_not",
]

