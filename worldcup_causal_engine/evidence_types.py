"""Typed evidence and observation schema (Phase 7–8).

This module keeps evidence typing as a *layer above* atoms/clusters.
It must not blur the boundary: Atom ≠ Event.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceType(StrEnum):
    OnlineRumor = "online_rumor"
    OfficialStatement = "official_statement"
    ConflictReport = "conflict_report"
    TransitComplaint = "transit_complaint"
    Other = "other"


CLAIM_TO_EVIDENCE: dict[str, EvidenceType] = {
    "blame_referee": EvidenceType.OnlineRumor,
    "blame_player": EvidenceType.OnlineRumor,
    "rumor_clip_shared": EvidenceType.OnlineRumor,
    "official_statement": EvidenceType.OfficialStatement,
    "fan_conflict_report": EvidenceType.ConflictReport,
    "transit_complaint": EvidenceType.TransitComplaint,
    "defend_referee": EvidenceType.OnlineRumor,
    "defend_player": EvidenceType.OnlineRumor,
}


def evidence_type_for_claim(claim_type: str) -> EvidenceType:
    return CLAIM_TO_EVIDENCE.get(claim_type, EvidenceType.Other)


class ObservationKey(StrEnum):
    """Standardized observation keys for Phase 8."""

    VerbalConflictIncidents = "verbal_conflict_incidents"
    ScuffleIncidents = "scuffle_incidents"
    RiotIncidents = "riot_incidents"
    PanicIncidents = "panic_incidents"

    RumorVolumeIndex = "rumor_volume_index"
    MediaOutrageIndex = "media_outrage_index"

