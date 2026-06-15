"""Parse SEC filing and transcript plain text into atom candidates."""

from __future__ import annotations

import re
from typing import Any

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.patterns import (
    infer_severity,
    infer_tone,
    match_rules,
    split_paragraphs,
    split_sentences,
)

_HEURISTIC_KEYWORDS = (
    "revenue",
    "earnings",
    "eps",
    "guidance",
    "outlook",
    "subscriber",
    "member",
    "miss",
    "beat",
    "decline",
    "forecast",
    "quarter",
    "expects",
    "million",
    "billion",
    "operating",
    "net income",
    "net loss",
    "growth",
    "margin",
    "gmv",
    "merchant",
)


def _capture_snippet(match, fallback: str) -> str:
    for i in range(1, (match.lastindex or 0) + 1):
        group = match.group(i)
        if group:
            return group.strip()[:280]
    return (match.group(0) or fallback).strip()[:280]


def _keyword_score(text: str) -> int:
    lower = text.lower()
    return sum(1 for kw in _HEURISTIC_KEYWORDS if kw in lower)


def _source_label_for_type(source_type: str) -> str:
    return "6-K" if source_type == "sec_6k" else "8-K"


def parse_sec_text(
    text: str,
    *,
    doc_id: str,
    source_type: str,
    published_offset_min: int,
    case_prefix: str,
    start_index: int = 0,
) -> tuple[list[MarketAtom], int]:
    atoms: list[MarketAtom] = []
    idx = start_index
    seen: set[str] = set()

    for sentence in split_sentences(text):
        norm = sentence.lower()[:120]
        if norm in seen:
            continue
        for rule, match in match_rules(sentence, source_type):
            seen.add(norm)
            snippet = _capture_snippet(match, sentence)
            if len(snippet) < 25:
                snippet = sentence[:280]

            meta: dict[str, Any] = dict(rule.metadata)
            meta["severity"] = infer_severity(snippet, rule.base_severity)
            meta["extracted_by"] = rule.rule_id
            meta["source_class"] = "primary_filing"

            if "transcript" in rule.tags:
                meta["tone"] = infer_tone(snippet)
            if rule.rule_id == "earnings_release":
                meta["miss_severity"] = meta["severity"]
            if "direction" in meta and any(w in snippet.lower() for w in ("rise", "jump", "surge", "up ")):
                meta["direction"] = -1.0

            atoms.append(
                MarketAtom(
                    atom_id=f"{case_prefix}_{idx:03d}",
                    text=snippet,
                    source=rule.source_label,
                    time=published_offset_min,
                    published_at=published_offset_min,
                    tags=list(rule.tags),
                    metadata=meta,
                )
            )
            idx += 1
            break

    return atoms, idx


def parse_sec_heuristic(
    text: str,
    *,
    source_type: str,
    published_offset_min: int,
    case_prefix: str,
    start_index: int = 0,
    max_atoms: int = 8,
) -> tuple[list[MarketAtom], int]:
    """Fallback: emit high-signal earnings paragraphs when regex rules miss."""
    atoms: list[MarketAtom] = []
    idx = start_index
    seen: set[str] = set()
    source_label = _source_label_for_type(source_type)

    ranked = sorted(split_paragraphs(text), key=_keyword_score, reverse=True)
    for paragraph in ranked:
        if _keyword_score(paragraph) < 2:
            continue
        norm = paragraph.lower()[:120]
        if norm in seen:
            continue
        seen.add(norm)
        snippet = paragraph[:280]
        severity = infer_severity(snippet, 0.72)
        meta: dict[str, Any] = {
            "severity": severity,
            "extracted_by": "heuristic_earnings",
            "source_class": "primary_filing",
            "tone": infer_tone(snippet),
        }
        if any(w in snippet.lower() for w in ("guidance", "outlook", "forecast", "expects")):
            meta["guidance_severity"] = severity
            tags = ["earnings", "guidance"]
        else:
            tags = ["earnings"]

        atoms.append(
            MarketAtom(
                atom_id=f"{case_prefix}_{idx:03d}",
                text=snippet,
                source=source_label,
                time=published_offset_min,
                published_at=published_offset_min,
                tags=tags,
                metadata=meta,
            )
        )
        idx += 1
        if len(atoms) >= max_atoms:
            break

    return atoms, idx


def parse_sec_document(
    text: str,
    *,
    doc_id: str,
    source_type: str,
    published_offset_min: int,
    case_prefix: str,
    heuristic_fallback: bool = True,
) -> tuple[list[MarketAtom], int]:
    """Pattern-based extraction with optional paragraph heuristic fallback."""
    atoms, idx = parse_sec_text(
        text,
        doc_id=doc_id,
        source_type=source_type,
        published_offset_min=published_offset_min,
        case_prefix=case_prefix,
    )
    if heuristic_fallback and not atoms:
        atoms, idx = parse_sec_heuristic(
            text,
            source_type=source_type,
            published_offset_min=published_offset_min,
            case_prefix=case_prefix,
            start_index=idx,
        )
    return atoms, idx
