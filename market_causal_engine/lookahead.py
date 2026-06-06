"""Look-ahead bias prevention for evidence feeds and case studies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from market_causal_engine.evidence import MarketAtom

# Sources that must not appear before their published_at in strict replay
POST_HOC_SOURCE_CLASSES = frozenset(
    {
        "post_mortem",
        "next_day_only",
        "calibration_label",
        "future_analyst",
    }
)

METADATA_FORWARD_KEYS = frozenset(
    {
        "miss_severity",
        "beat_severity",
        "guidance_severity",
        "tone",
        "direction",
        "hawkish",
        "hot_print",
        "credibility",
        "strength",
    }
)


@dataclass(frozen=True)
class LookAheadPolicy:
    """Controls which atoms may enter the causal kernel at simulation time as_of."""

    strict: bool = True
    forbid_post_hoc_sources: bool = True
    forbidden_source_classes: tuple[str, ...] = tuple(POST_HOC_SOURCE_CLASSES)
    max_published_skew: int = 0  # published_at must not exceed time by more than N minutes

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LookAheadPolicy:
        if not data:
            return cls()
        forbidden = tuple(data.get("forbidden_source_classes", POST_HOC_SOURCE_CLASSES))
        return cls(
            strict=bool(data.get("strict", True)),
            forbid_post_hoc_sources=bool(data.get("forbid_post_hoc_sources", True)),
            forbidden_source_classes=forbidden,
            max_published_skew=int(data.get("max_published_skew", 0)),
        )


@dataclass
class AtomValidation:
    atom_id: str
    accepted: bool
    reason_code: str
    detail: str = ""
    published_at: int = 0
    simulation_time: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "accepted": self.accepted,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "published_at": self.published_at,
            "simulation_time": self.simulation_time,
        }


@dataclass
class LookAheadReport:
    as_of: int
    policy: LookAheadPolicy
    validations: list[AtomValidation] = field(default_factory=list)

    @property
    def accepted_atoms(self) -> list[AtomValidation]:
        return [v for v in self.validations if v.accepted]

    @property
    def rejected_atoms(self) -> list[AtomValidation]:
        return [v for v in self.validations if not v.accepted]

    @property
    def passed(self) -> bool:
        return len(self.rejected_atoms) == 0

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_atoms)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_atoms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "policy": {
                "strict": self.policy.strict,
                "forbid_post_hoc_sources": self.policy.forbid_post_hoc_sources,
                "forbidden_source_classes": list(self.policy.forbidden_source_classes),
            },
            "passed": self.passed,
            "accepted_count": len(self.accepted_atoms),
            "rejected_count": len(self.rejected_atoms),
            "validations": [v.to_dict() for v in self.validations],
            "rejected": [v.to_dict() for v in self.rejected_atoms],
        }


def validate_atom(
    atom: MarketAtom,
    *,
    as_of: int,
    policy: LookAheadPolicy | None = None,
) -> AtomValidation:
    """Return whether atom is admissible at simulation horizon as_of."""
    policy = policy or LookAheadPolicy()
    pub = atom.published_at if atom.published_at is not None else atom.time
    sim_t = int(atom.time)

    if pub > as_of:
        return AtomValidation(
            atom_id=atom.atom_id,
            accepted=False,
            reason_code="lookahead_published_at",
            detail=f"published_at={pub} exceeds as_of={as_of}",
            published_at=pub,
            simulation_time=sim_t,
        )

    if sim_t > as_of:
        return AtomValidation(
            atom_id=atom.atom_id,
            accepted=False,
            reason_code="lookahead_simulation_time",
            detail=f"time={sim_t} exceeds as_of={as_of}",
            published_at=pub,
            simulation_time=sim_t,
        )

    if policy.strict and pub > sim_t + policy.max_published_skew:
        return AtomValidation(
            atom_id=atom.atom_id,
            accepted=False,
            reason_code="published_after_event_time",
            detail=f"published_at={pub} > time={sim_t} (possible look-ahead labeling error)",
            published_at=pub,
            simulation_time=sim_t,
        )

    source_class = atom.metadata.get("source_class", "")
    if policy.forbid_post_hoc_sources and source_class in policy.forbidden_source_classes:
        return AtomValidation(
            atom_id=atom.atom_id,
            accepted=False,
            reason_code="forbidden_post_hoc_source",
            detail=f"source_class={source_class!r} not allowed in strict replay",
            published_at=pub,
            simulation_time=sim_t,
        )

    if atom.metadata.get("uses_future_price") is True and pub <= as_of:
        return AtomValidation(
            atom_id=atom.atom_id,
            accepted=False,
            reason_code="future_price_leak",
            detail="metadata.uses_future_price=true",
            published_at=pub,
            simulation_time=sim_t,
        )

    if atom.metadata.get("available_from") is not None:
        try:
            available = int(atom.metadata["available_from"])
            if available > as_of:
                return AtomValidation(
                    atom_id=atom.atom_id,
                    accepted=False,
                    reason_code="lookahead_available_from",
                    detail=f"available_from={available} exceeds as_of={as_of}",
                    published_at=pub,
                    simulation_time=sim_t,
                )
        except (TypeError, ValueError):
            pass

    return AtomValidation(
        atom_id=atom.atom_id,
        accepted=True,
        reason_code="accepted",
        published_at=pub,
        simulation_time=sim_t,
    )


def validate_feed(
    atoms: list[MarketAtom],
    *,
    as_of: int,
    policy: LookAheadPolicy | None = None,
) -> LookAheadReport:
    policy = policy or LookAheadPolicy()
    report = LookAheadReport(as_of=as_of, policy=policy)
    for atom in atoms:
        report.validations.append(validate_atom(atom, as_of=as_of, policy=policy))
    return report


def filter_admissible_atoms(
    atoms: list[MarketAtom],
    *,
    as_of: int,
    policy: LookAheadPolicy | None = None,
) -> tuple[list[MarketAtom], LookAheadReport]:
    report = validate_feed(atoms, as_of=as_of, policy=policy)
    accepted_ids = {v.atom_id for v in report.accepted_atoms}
    filtered = [a for a in atoms if a.atom_id in accepted_ids]
    filtered.sort(key=lambda a: (a.published_at, a.time, a.atom_id))
    return filtered, report
