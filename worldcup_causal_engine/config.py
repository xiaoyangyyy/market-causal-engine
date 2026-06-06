"""Kernel runtime configuration including ablation switches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KernelConfig:
    """Controls kernel behaviour; ablation flags disable subsystems."""

    use_flags: bool = True
    use_resources: bool = True
    use_priority: bool = True
    use_trace: bool = True
    use_interventions: bool = True
    use_evidence_ledger: bool = True
    use_contracts: bool = True
    use_causal_ledger: bool = True
    ablation_id: str = "full"

    @classmethod
    def full(cls) -> KernelConfig:
        return cls(ablation_id="full")

    @classmethod
    def ablation(cls, ablation_id: str) -> KernelConfig:
        mapping = {
            "A1": {"use_flags": False},
            "A2": {"use_resources": False},
            "A3": {"use_priority": False},
            "A4": {"use_trace": False},
            "A5": {"use_interventions": False},
            "A6": {"use_evidence_ledger": False},
        }
        overrides = mapping.get(ablation_id, {})
        return cls(ablation_id=ablation_id, **overrides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ablation_id": self.ablation_id,
            "use_flags": self.use_flags,
            "use_resources": self.use_resources,
            "use_priority": self.use_priority,
            "use_trace": self.use_trace,
            "use_interventions": self.use_interventions,
            "use_evidence_ledger": self.use_evidence_ledger,
            "use_contracts": self.use_contracts,
            "use_causal_ledger": self.use_causal_ledger,
        }


ABLATION_IDS = ["full", "A1", "A2", "A3", "A4", "A5", "A6"]

ABLATION_LABELS = {
    "full": "Full system",
    "A1": "without_flags",
    "A2": "without_resources",
    "A3": "without_priority",
    "A4": "without_trace",
    "A5": "without_intervention",
    "A6": "without_evidence_ledger",
}
