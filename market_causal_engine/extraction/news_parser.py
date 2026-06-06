"""Parse news feed JSONL and headlines into atom candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.patterns import infer_severity, infer_tone, match_rules


def _capture_snippet(match, fallback: str) -> str:
    for i in range(1, (match.lastindex or 0) + 1):
        group = match.group(i)
        if group:
            return group.strip()[:280]
    return (match.group(0) or fallback).strip()[:280]


def parse_news_record(
    record: dict[str, Any],
    *,
    case_prefix: str,
    index: int,
    default_source_type: str = "news",
) -> list[MarketAtom]:
    headline = record.get("headline") or record.get("text") or record.get("title", "")
    body = record.get("body") or record.get("summary") or ""
    text = f"{headline}. {body}".strip()
    offset = int(record.get("published_offset_min", record.get("time", 0)))
    source = record.get("source", "news")
    source_type = record.get("source_type", default_source_type)

    atoms: list[MarketAtom] = []
    idx = index
    for rule, match in match_rules(text, source_type):
        snippet = _capture_snippet(match, headline or text)
        meta: dict[str, Any] = dict(rule.metadata)
        meta["severity"] = infer_severity(snippet, rule.base_severity)
        meta["extracted_by"] = rule.rule_id
        meta["source_class"] = record.get("source_class", "news_wire")
        if record.get("metadata"):
            meta.update(dict(record["metadata"]))
        if "transcript" in rule.tags:
            meta["tone"] = infer_tone(snippet)
        if "direction" in meta and any(w in snippet.lower() for w in ("rise", "jump", "surge", "up ")):
            meta["direction"] = -1.0

        record_tags = list(record.get("tags") or [])
        tags = list(dict.fromkeys(record_tags + list(rule.tags)))

        atoms.append(
            MarketAtom(
                atom_id=f"{case_prefix}_{idx:03d}",
                text=snippet,
                source=source,
                time=offset,
                published_at=int(record.get("published_at", offset)),
                tags=tags,
                metadata=meta,
            )
        )
        idx += 1
        break
    else:
        if headline and len(headline) >= 20:
            meta = {
                "severity": infer_severity(headline, 0.65),
                "extracted_by": "headline_fallback",
                "source_class": record.get("source_class", "news_wire"),
            }
            if record.get("metadata"):
                meta.update(dict(record["metadata"]))
            tags = list(record.get("tags", ["news"]))
            atoms.append(
                MarketAtom(
                    atom_id=f"{case_prefix}_{idx:03d}",
                    text=headline[:280],
                    source=source,
                    time=offset,
                    published_at=int(record.get("published_at", offset)),
                    tags=tags,
                    metadata=meta,
                )
            )
    return atoms


def parse_news_jsonl(
    path: Path,
    *,
    case_prefix: str,
    start_index: int = 0,
) -> tuple[list[MarketAtom], int]:
    atoms: list[MarketAtom] = []
    idx = start_index
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            batch = parse_news_record(record, case_prefix=case_prefix, index=idx)
            atoms.extend(batch)
            idx += len(batch)
    return atoms, idx
