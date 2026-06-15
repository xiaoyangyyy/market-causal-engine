"""Catalog atom enrichment: polarity, boilerplate filtering, earnings beat/miss hints."""

from __future__ import annotations

import copy
import re
from typing import Any

from market_causal_engine.evidence import MarketAtom

BEAT_KEYWORDS = (
    "beat estimates",
    "beats estimates",
    "beat expectations",
    "exceeded expectations",
    "above expectations",
    "record revenue",
    "record earnings",
    "record quarter",
    "year-over-year growth",
    "yoy growth",
    "strong quarter",
    "raised guidance",
    "raising guidance",
    "increase guidance",
    "subscriber growth",
    "revenue grew",
    "earnings grew",
    "operating income grew",
    "net income rose",
    "surpassed",
)

MISS_KEYWORDS = (
    "missed estimates",
    "miss estimates",
    "below expectations",
    "fell short",
    "short of",
    "lowered guidance",
    "lowers guidance",
    "cut guidance",
    "reduced guidance",
    "decline in revenue",
    "revenue declined",
    "revenue fell",
    "net loss",
    "operating loss",
    "subscriber loss",
    "lost subscribers",
    "disappointed",
    "weaker than expected",
    "slowing growth",
    "slow materially",
)

BOILERPLATE_PATTERNS = (
    "forward-looking statement",
    "forward-looking statements",
    "private securities litigation reform act",
    "safe harbor",
    "should not be relied upon",
    "not historical facts",
    "cautionary statement",
    "risk factors",
    "undue reliance",
)

_FINANCIAL_NUM = re.compile(r"\d[\d,]*\.?\d*\s*(?:%|percent|million|billion)")


def score_text_polarity(text: str) -> dict[str, float]:
    """Return bull/bear/boilerplate scores for catalog filing text."""
    lower = text.lower()
    bull = sum(1 for kw in BEAT_KEYWORDS if kw in lower)
    bear = sum(1 for kw in MISS_KEYWORDS if kw in lower)
    boiler = sum(1 for pat in BOILERPLATE_PATTERNS if pat in lower)
    has_numbers = 1.0 if _FINANCIAL_NUM.search(text) else 0.0
    return {
        "bull": float(bull),
        "bear": float(bear),
        "boilerplate": float(boiler),
        "has_numbers": has_numbers,
        "net": float(bull - bear),
    }


def enrich_catalog_atom(atom: MarketAtom) -> MarketAtom:
    """Add catalog-safe metadata for compiler payload and direction features."""
    meta = dict(atom.metadata)
    scores = score_text_polarity(atom.text)
    meta["catalog_bull"] = scores["bull"]
    meta["catalog_bear"] = scores["bear"]
    meta["catalog_polarity"] = scores["net"]
    meta["catalog_boilerplate"] = scores["boilerplate"] >= 1.0 and scores["bull"] + scores["bear"] == 0

    base_sev = float(meta.get("severity", 0.1))
    if meta["catalog_boilerplate"]:
        base_sev *= 0.12
    elif scores["has_numbers"] and scores["bull"] + scores["bear"] == 0:
        base_sev *= 0.65
    meta["severity"] = round(base_sev, 4)

    net = scores["net"]
    if net > 0:
        meta["beat_severity"] = round(min(0.92, 0.42 + 0.08 * net), 3)
        meta["miss_severity"] = 0.12
    elif net < 0:
        meta["miss_severity"] = round(min(0.92, 0.42 + 0.08 * abs(net)), 3)
        meta["beat_severity"] = 0.12
    else:
        meta["beat_severity"] = 0.38
        meta["miss_severity"] = 0.38

    tags = list(atom.tags)
    if meta["catalog_boilerplate"] and "boilerplate" not in tags:
        tags.append("boilerplate")
    return MarketAtom(
        atom_id=atom.atom_id,
        text=atom.text,
        source=atom.source,
        time=atom.time,
        tags=tags,
        metadata=meta,
        published_at=atom.published_at,
    )


def enrich_catalog_atoms(atoms: list[MarketAtom]) -> list[MarketAtom]:
    return [enrich_catalog_atom(a) for a in atoms]


def catalog_atom_summary(atoms: list[MarketAtom]) -> dict[str, Any]:
    """Aggregate atom-level signals for severity scaling and direction features."""
    if not atoms:
        return {
            "atom_count": 0,
            "bull_total": 0.0,
            "bear_total": 0.0,
            "net_polarity": 0.0,
            "max_severity": 0.0,
            "boilerplate_ratio": 0.0,
            "financial_atom_count": 0,
        }
    bull = sum(float(a.metadata.get("catalog_bull", 0)) for a in atoms)
    bear = sum(float(a.metadata.get("catalog_bear", 0)) for a in atoms)
    boiler = sum(1 for a in atoms if a.metadata.get("catalog_boilerplate"))
    fin = sum(1 for a in atoms if a.metadata.get("extracted_by") == "financial_results")
    max_sev = max(float(a.metadata.get("severity", 0.0)) for a in atoms)
    return {
        "atom_count": len(atoms),
        "bull_total": bull,
        "bear_total": bear,
        "net_polarity": bull - bear,
        "max_severity": max_sev,
        "boilerplate_ratio": round(boiler / len(atoms), 4),
        "financial_atom_count": fin,
    }


def apply_catalog_evidence_scale(atoms: list[MarketAtom], scale: float) -> list[MarketAtom]:
    """Scale atom severities for mild / mixed filing evidence."""
    if scale >= 0.999:
        return atoms
    scaled: list[MarketAtom] = []
    for atom in atoms:
        meta = copy.deepcopy(atom.metadata)
        meta["severity"] = round(float(meta.get("severity", 0.1)) * scale, 4)
        for key in ("beat_severity", "miss_severity"):
            if key in meta:
                meta[key] = round(float(meta[key]) * scale, 4)
        scaled.append(
            MarketAtom(
                atom_id=atom.atom_id,
                text=atom.text,
                source=atom.source,
                time=atom.time,
                tags=list(atom.tags),
                metadata=meta,
                published_at=atom.published_at,
            )
        )
    return scaled
