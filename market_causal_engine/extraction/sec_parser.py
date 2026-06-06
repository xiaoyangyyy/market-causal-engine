"""Parse SEC filing and transcript plain text into atom candidates."""

from __future__ import annotations

from typing import Any

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.patterns import (
    infer_severity,
    infer_tone,
    match_rules,
    split_sentences,
)


def _capture_snippet(match, fallback: str) -> str:
    for i in range(1, (match.lastindex or 0) + 1):
        group = match.group(i)
        if group:
            return group.strip()[:280]
    return (match.group(0) or fallback).strip()[:280]


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
