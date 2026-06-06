"""Proposals from untrusted proposers (LLM, human, rules)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Proposal:
    """Untrusted event proposal — must pass verification before execution."""

    id: str
    kind: str
    time: int
    payload: dict[str, Any] = field(default_factory=dict)
    proposer: str = "unknown"  # llm | human | rules | scenario
    confidence: float = 1.0
    evidence_refs: list[str] = field(default_factory=list)
    priority: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "time": self.time,
            "payload": self.payload,
            "proposer": self.proposer,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "priority": self.priority,
        }


@dataclass
class VerificationResult:
    proposal_id: str
    kind: str
    accepted: bool
    reason_code: str  # accepted | missing_flags | resource_shortage | pre_condition | proposal_too_late | ineffective_intervention | unknown_kind | no_contract
    detail: str = ""
    missing_flags: list[str] = field(default_factory=list)
    missing_resources: dict[str, float] = field(default_factory=dict)
    failed_pre: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "accepted": self.accepted,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "missing_flags": self.missing_flags,
            "missing_resources": self.missing_resources,
            "failed_pre": self.failed_pre,
        }
