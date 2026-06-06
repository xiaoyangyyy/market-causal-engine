"""Build event-level MDG from contracts/specs and runtime trace."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from worldcup_causal_engine.ir.contract import get_contract
from worldcup_causal_engine.mdg.graph import EdgeEvidence, EventMDG, MDGNode
from worldcup_causal_engine.registry import MECHANISM_INDEX, get_spec


def _flag_producers_from_trace(trace: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    """Map flag -> counter(kind_that_set_it)."""
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for e in trace:
        if e.get("action") != "set_flag":
            continue
        flags_delta = e.get("flags_delta") or {}
        kind = e.get("kind", "")
        if not kind:
            continue
        for flag, op in flags_delta.items():
            if op == "set":
                out[flag][kind] += 1
    return dict(out)


def _successor_counts(trace: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    executed = [e for e in trace if e.get("action") == "executed"]
    pairs: list[tuple[str, str]] = []
    for a, b in zip(executed, executed[1:]):
        ka = a.get("kind", "")
        kb = b.get("kind", "")
        if ka and kb and ka != kb:
            pairs.append((ka, kb))
    return Counter(pairs)


def build_event_mdg_from_result(result: dict[str, Any]) -> EventMDG:
    """Primary builder: include static edges + runtime evidences from a single run."""
    trace = result.get("trace", [])
    mdg = EventMDG(meta={"scenario_id": result.get("scenario_id", ""), "world_id": result.get("world_id", "")})

    # Nodes: union of all known mechanism kinds + any trace kinds.
    kinds = set(MECHANISM_INDEX.keys())
    for e in trace:
        k = e.get("kind")
        if k:
            kinds.add(k)

    for kind in sorted(kinds):
        spec = get_spec(kind)
        contract = get_contract(kind)
        resources: dict[str, float] = {}
        waits: list[str] = []
        if contract:
            waits = list(contract.waits)
            for name, amount in contract.resources:
                resources[name] = float(amount)
        elif spec:
            waits = list(spec.waits)
            for r in spec.resources:
                resources[r] = 1.0

        mdg.upsert_node(
            MDGNode(
                kind=kind,
                waits=sorted(set(waits)),
                resources=resources,
                contract_version=contract.version if contract else None,
                spec_version=spec.version if spec else None,
            )
        )

    # Static edges: emits.
    for kind in kinds:
        spec = get_spec(kind)
        contract = get_contract(kind)
        if contract and contract.emits:
            for dst in contract.emits:
                mdg.add_edge(
                    kind,
                    dst,
                    EdgeEvidence(
                        edge_type="contract_emits",
                        weight=1.0,
                        detail=f"contract:{contract.version}",
                        sources=[f"contract:{kind}"],
                    ),
                )
        if spec and spec.emits:
            for dst in spec.emits:
                mdg.add_edge(
                    kind,
                    dst,
                    EdgeEvidence(
                        edge_type="spec_emits",
                        weight=1.0,
                        detail=f"spec:{spec.version}",
                        sources=[f"spec:{kind}"],
                    ),
                )

    # Runtime edges: trace successors.
    succ = _successor_counts(trace)
    for (src, dst), count in succ.items():
        mdg.add_edge(
            src,
            dst,
            EdgeEvidence(
                edge_type="trace_successor",
                weight=float(count),
                count=int(count),
                detail="observed_successor",
                sources=["trace:executed_adjacent"],
            ),
        )

    # Flag wait edges: producer(kind_that_sets_flag) -> consumer(kind_waits_flag)
    producers = _flag_producers_from_trace(trace)
    for consumer_kind, node in mdg.nodes.items():
        for flag in node.waits:
            prod = producers.get(flag)
            if not prod:
                continue
            # choose most common producer for a single-run graph
            producer_kind, count = prod.most_common(1)[0]
            mdg.add_edge(
                producer_kind,
                consumer_kind,
                EdgeEvidence(
                    edge_type="flag_wait",
                    weight=float(count),
                    count=int(count),
                    detail=f"flag:{flag}",
                    sources=[f"trace:set_flag:{flag}"],
                ),
            )

    return mdg

