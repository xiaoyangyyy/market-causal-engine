"""Mechanism contracts: pre/post conditions for Proposal-Verification runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StateConstraint:
    """e.g. rumor_volume must be < 0.6 before official_clarification can clear spike."""

    variable: str
    op: str  # "<", "<=", ">", ">=", "=="
    value: float

    def check(self, state: dict[str, float]) -> bool:
        actual = state.get(self.variable, 0.0)
        if self.op == "<":
            return actual < self.value
        if self.op == "<=":
            return actual <= self.value
        if self.op == ">":
            return actual > self.value
        if self.op == ">=":
            return actual >= self.value
        if self.op == "==":
            return abs(actual - self.value) < 1e-6
        return False

    def describe(self) -> str:
        return f"{self.variable}{self.op}{self.value}"


@dataclass(frozen=True)
class Contract:
    kind: str
    version: str = "v0.2"
    waits: tuple[str, ...] = ()
    resources: tuple[tuple[str, float], ...] = ()  # (name, amount)
    pre: tuple[StateConstraint, ...] = ()
    post: tuple[StateConstraint, ...] = ()  # checked after handler if enabled
    emits: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, kind: str, data: dict[str, Any]) -> Contract:
        pre = tuple(
            StateConstraint(c["variable"], c["op"], float(c["value"]))
            for c in data.get("pre", [])
        )
        post = tuple(
            StateConstraint(c["variable"], c["op"], float(c["value"]))
            for c in data.get("post", [])
        )
        resources = tuple(
            (r["name"], float(r["amount"]))
            for r in data.get("resources", [])
        )
        return cls(
            kind=kind,
            version=data.get("version", "v0.2"),
            waits=tuple(data.get("waits", [])),
            resources=resources,
            pre=pre,
            post=post,
            emits=tuple(data.get("emits", [])),
        )


CONTRACT_INDEX: dict[str, Contract] = {}


def _load_default_contracts() -> None:
    path = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "contracts" / "v0.1.json"
    if not path.exists():
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    for kind, spec in raw.items():
        CONTRACT_INDEX[kind] = Contract.from_dict(kind, spec)


def get_contract(kind: str) -> Contract | None:
    if not CONTRACT_INDEX:
        _load_default_contracts()
    return CONTRACT_INDEX.get(kind)


def register_contract(contract: Contract) -> None:
    CONTRACT_INDEX[contract.kind] = contract
