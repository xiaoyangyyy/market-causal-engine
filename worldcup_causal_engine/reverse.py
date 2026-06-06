"""Reverse debugger: trace analysis, blockage explanation, intervention diff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_causal_engine.constants import RISK_KEYS
from worldcup_causal_engine.registry import MECHANISM_INDEX


@dataclass
class TraceRecord:
    event_id: str
    kind: str
    time: int
    action: str
    patch: dict[str, float] = field(default_factory=dict)
    flags_delta: dict[str, str] = field(default_factory=dict)
    resource_delta: dict[str, float] = field(default_factory=dict)
    cause: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


def _normalize_trace(trace: list[Any]) -> list[TraceRecord]:
    records: list[TraceRecord] = []
    for entry in trace:
        if isinstance(entry, TraceRecord):
            records.append(entry)
        elif isinstance(entry, dict):
            records.append(
                TraceRecord(
                    event_id=entry.get("event_id", ""),
                    kind=entry.get("kind", ""),
                    time=int(entry.get("time", 0)),
                    action=entry.get("action", ""),
                    patch=dict(entry.get("patch", {})),
                    flags_delta=dict(entry.get("flags_delta", {})),
                    resource_delta=dict(entry.get("resource_delta", {})),
                    cause=list(entry.get("cause", [])),
                    blocked_reason=entry.get("blocked_reason"),
                )
            )
    return records


class ReverseDebugger:
    def __init__(
        self,
        trace: list[Any],
        final_state: dict[str, float] | None = None,
        mechanism_index: dict | None = None,
    ):
        self.trace = _normalize_trace(trace)
        self.final_state = final_state or {}
        self.mechanism_index = mechanism_index or MECHANISM_INDEX
        self._by_event: dict[str, list[TraceRecord]] = {}
        self._executed_causes: dict[str, list[str]] = {}
        for entry in self.trace:
            self._by_event.setdefault(entry.event_id, []).append(entry)
            if entry.action == "executed":
                self._executed_causes[entry.event_id] = list(entry.cause)

    def _executed_kinds(self) -> list[str]:
        kinds: list[str] = []
        for entry in self.trace:
            if entry.action == "executed":
                kinds.append(entry.kind)
        return kinds

    def _resolve_cause_chain(self, event_id: str) -> list[str]:
        chain: list[str] = []
        visited: set[str] = set()
        current = event_id

        while current and current not in visited:
            visited.add(current)
            entries = self._by_event.get(current, [])
            kind = entries[0].kind if entries else current
            chain.append(kind)

            causes = self._executed_causes.get(current, [])
            parent_id = None
            for cause in causes:
                if cause.startswith("event:"):
                    parent_id = cause.split(":", 1)[1]
                    break
            current = parent_id or ""

        chain.reverse()
        deduped: list[str] = []
        for kind in chain:
            if not deduped or deduped[-1] != kind:
                deduped.append(kind)
        return deduped

    def trace_path(self, event_id: str) -> list[str]:
        if event_id not in self._by_event:
            return []
        return self._resolve_cause_chain(event_id)

    def why_blocked(self, event_id: str) -> dict[str, Any]:
        entries = self._by_event.get(event_id, [])
        blocked = [e for e in entries if e.action == "blocked"]
        if not blocked:
            return {"event_id": event_id, "blocked": False, "reason": None}

        entry = blocked[-1]
        reason = entry.blocked_reason or "unknown"
        result: dict[str, Any] = {
            "event_id": event_id,
            "kind": entry.kind,
            "time": entry.time,
            "blocked": True,
            "reason": reason,
        }
        if reason.startswith("missing_flags:"):
            result["missing_flags"] = reason.split(":", 1)[1].split(",")
        elif reason.startswith("resource_shortage:"):
            result["resource"] = reason.split(":", 1)[1]
            result["required"] = entry.resource_delta
        elif reason.startswith("condition_not_met:"):
            result["condition"] = reason.split(":", 1)[1]
        return result

    def why_not_happen(self, kind: str) -> dict[str, Any]:
        executed = kind in self._executed_kinds()
        blocked_entries = [
            e for e in self.trace if e.kind == kind and e.action == "blocked"
        ]
        if executed:
            return {"kind": kind, "happened": True, "reason": None}

        if blocked_entries:
            reasons = [e.blocked_reason for e in blocked_entries if e.blocked_reason]
            return {
                "kind": kind,
                "happened": False,
                "reason": "blocked",
                "blocked_reasons": reasons,
                "count": len(blocked_entries),
            }

        spec = self.mechanism_index.get(kind)
        if spec and spec.waits:
            return {
                "kind": kind,
                "happened": False,
                "reason": "never_scheduled_or_missing_prerequisites",
                "required_flags": list(spec.waits),
            }

        return {"kind": kind, "happened": False, "reason": "never_scheduled"}

    def resource_bottlenecks(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for entry in self.trace:
            if entry.action == "blocked" and entry.blocked_reason:
                if entry.blocked_reason.startswith("resource_shortage:"):
                    resource = entry.blocked_reason.split(":", 1)[1]
                    counts[resource] = counts.get(resource, 0) + 1
        return [
            {"resource": resource, "failures": count}
            for resource, count in sorted(counts.items(), key=lambda x: -x[1])
        ]

    def flag_lifecycle(self, flag: str) -> list[tuple[int, str]]:
        lifecycle: list[tuple[int, str]] = []
        for entry in self.trace:
            if flag in entry.flags_delta:
                lifecycle.append((entry.time, entry.flags_delta[flag]))
        return lifecycle

    def variable_history(self, variable: str) -> list[tuple[int, float]]:
        history: list[tuple[int, float]] = []
        cumulative = 0.0
        for entry in self.trace:
            if entry.action == "commit" and variable in entry.patch:
                cumulative += entry.patch[variable]
                history.append((entry.time, round(cumulative, 4)))
        if not history and variable in self.final_state:
            history.append((0, float(self.final_state[variable])))
        return history

    def dominant_risk_path(self) -> list[str]:
        best_entry: TraceRecord | None = None
        best_delta = 0.0

        for entry in self.trace:
            if entry.action != "commit":
                continue
            for risk_key in RISK_KEYS:
                if risk_key in entry.patch and entry.patch[risk_key] > best_delta:
                    best_delta = entry.patch[risk_key]
                    best_entry = entry

        if best_entry is None:
            return self._dedupe_path(self._executed_kinds())

        return self._dedupe_path(self._resolve_cause_chain(best_entry.event_id))

    @staticmethod
    def _dedupe_path(kinds: list[str]) -> list[str]:
        deduped: list[str] = []
        for kind in kinds:
            if not deduped or deduped[-1] != kind:
                deduped.append(kind)
        return deduped

    def diff_trace(self, other: ReverseDebugger) -> dict[str, Any]:
        path_a = self._dedupe_path(self._executed_kinds())
        path_b = self._dedupe_path(other._executed_kinds())

        fork_point: str | None = None
        shared_len = 0
        for i, (a, b) in enumerate(zip(path_a, path_b)):
            if a == b:
                shared_len = i + 1
                fork_point = a
            else:
                break

        only_a = path_a[shared_len:]
        only_b = path_b[shared_len:]

        return {
            "fork_point": fork_point,
            "path_a": path_a,
            "path_b": path_b,
            "only_a": only_a,
            "only_b": only_b,
            "diverged": path_a != path_b,
        }

    def evidence_links(self) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        for entry in self.trace:
            if entry.action != "executed":
                continue
            for cause in entry.cause:
                if cause.startswith("claim_cluster:"):
                    links.append(
                        {
                            "event_id": entry.event_id,
                            "event_kind": entry.kind,
                            "time": entry.time,
                            "cluster_id": cause.split(":", 1)[1],
                        }
                    )
        return links

    def trace_to_evidence(self, event_id: str) -> list[str]:
        """Return cluster ids in the causal ancestry of an event."""
        clusters: list[str] = []
        entries = self._by_event.get(event_id, [])
        if not entries:
            return clusters

        visited: set[str] = set()
        stack = list(self._executed_causes.get(event_id, []))
        while stack:
            cause = stack.pop()
            if cause.startswith("claim_cluster:"):
                cid = cause.split(":", 1)[1]
                if cid not in visited:
                    visited.add(cid)
                    clusters.append(cid)
            elif cause.startswith("event:"):
                parent_id = cause.split(":", 1)[1]
                stack.extend(self._executed_causes.get(parent_id, []))
        return clusters

    def explain(self, scenario_id: str = "", world_id: str = "") -> str:
        lines: list[str] = []
        header = f"Scenario: {scenario_id or 'unknown'} | World: {world_id or 'unknown'}"
        lines.append(header)
        lines.append("")

        path = self.dominant_risk_path()
        lines.append("Dominant risk path:")
        lines.append("  " + " → ".join(path) if path else "  (empty)")
        lines.append("")

        bottlenecks = self.resource_bottlenecks()
        if bottlenecks:
            lines.append("Resource bottlenecks:")
            for item in bottlenecks:
                lines.append(f"  - {item['resource']}: {item['failures']} failure(s)")
        else:
            lines.append("Resource bottlenecks: none")
        lines.append("")

        blocked_kinds = sorted(
            {e.kind for e in self.trace if e.action == "blocked"}
        )
        if blocked_kinds:
            lines.append("Blocked events:")
            for kind in blocked_kinds:
                entries = [e for e in self.trace if e.kind == kind and e.action == "blocked"]
                if entries:
                    lines.append(f"  - {kind}: {entries[-1].blocked_reason}")
        lines.append("")

        evidence = self.evidence_links()
        if evidence:
            lines.append("Evidence links:")
            for link in evidence:
                lines.append(
                    f"  - {link['event_kind']} @ t{link['time']} ← cluster {link['cluster_id']}"
                )
            lines.append("")

        if self.final_state:
            lines.append("Final risk:")
            for key in RISK_KEYS:
                short = key.replace("_risk", "")
                lines.append(f"  - {short}: {round(self.final_state.get(key, 0.0), 4)}")

        return "\n".join(lines)


def analyze_result(result: dict[str, Any]) -> ReverseDebugger:
    return ReverseDebugger(
        trace=result.get("trace", []),
        final_state=result.get("final_state", {}),
    )


def diff_results(run_a: dict[str, Any], run_b: dict[str, Any]) -> dict[str, Any]:
    dbg_a = analyze_result(run_a)
    dbg_b = analyze_result(run_b)
    diff = dbg_a.diff_trace(dbg_b)
    diff["scenario_id"] = run_a.get("scenario_id")
    diff["world_a"] = run_a.get("world_id")
    diff["world_b"] = run_b.get("world_id")
    diff["final_risk_a"] = run_a.get("final_risk")
    diff["final_risk_b"] = run_b.get("final_risk")
    return diff
