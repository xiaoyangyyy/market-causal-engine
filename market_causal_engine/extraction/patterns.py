"""Extraction pattern library and tag inference."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --- Severity heuristics ---

NEGATIVE_TERMS = (
    "miss",
    "missed",
    "loss",
    "decline",
    "cut",
    "lower",
    "weak",
    "worse",
    "disappoint",
    "shortfall",
    "slowdown",
    "fraud",
    "probe",
    "investigation",
    "hawkish",
    "surprise hike",
    "hot cpi",
)
POSITIVE_TERMS = ("beat", "raised", "upgrade", "strong", "exceeded", "record")


@dataclass(frozen=True)
class ExtractionRule:
    rule_id: str
    source_types: tuple[str, ...]
    pattern: re.Pattern[str]
    tags: tuple[str, ...]
    source_label: str
    base_severity: float = 0.7
    metadata: dict[str, Any] = field(default_factory=dict)


def infer_tone(text: str) -> float:
    lower = text.lower()
    neg = sum(1 for t in NEGATIVE_TERMS if t in lower)
    pos = sum(1 for t in POSITIVE_TERMS if t in lower)
    if neg == pos == 0:
        return -0.3 if "?" not in text else 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(neg + pos, 1)))


def infer_severity(text: str, base: float = 0.7) -> float:
    lower = text.lower()
    boost = 0.0
    if any(w in lower for w in ("massive", "plunge", "crash", "fraud", "surprise")):
        boost += 0.12
    if re.search(r"\d{2,3}%", lower):
        boost += 0.08
    if "miss" in lower or "cut" in lower:
        boost += 0.05
    return round(min(0.98, base + boost), 3)


EXTRACTION_RULES: list[ExtractionRule] = [
    ExtractionRule(
        "earnings_release",
        ("sec_8k", "sec_filing", "press_release"),
        re.compile(
            r"(reports?\s+(?:q[1-4]|first|second|third|fourth).{0,40}(?:miss|beat|revenue|eps|subscriber|earnings))"
            r"|((?:revenue|eps|subscriber).{0,30}(?:miss|beat|decline|loss))"
            r"|(missing\s+wall\s+street\s+estimates)"
            r"|(earnings\s+miss\s+relative\s+to)",
            re.I,
        ),
        ("earnings",),
        "8-K",
        0.85,
        {"miss_severity": 0.85},
    ),
    ExtractionRule(
        "user_metric_decline",
        ("sec_8k", "press_release", "transcript", "news"),
        re.compile(
            r"((?:daily\s+active\s+users?|dau|mau).{0,40}(?:declin|decreas|fell|drop))"
            r"|((?:users?).{0,30}declined\s+sequentially)",
            re.I,
        ),
        ("earnings", "user_metrics"),
        "8-K",
        0.82,
    ),
    ExtractionRule(
        "guidance_cut",
        ("sec_8k", "sec_filing", "press_release", "transcript"),
        re.compile(
            r"(lower(?:s|ed)?\s+(?:guidance|outlook|forecast|revenue|fy))"
            r"|(guidance.{0,20}cut)"
            r"|(expects?.{0,30}(?:decline|decrease|lower|slow))",
            re.I,
        ),
        ("earnings", "guidance"),
        "guidance",
        0.88,
        {"guidance_severity": 0.85},
    ),
    ExtractionRule(
        "ad_revenue_miss",
        ("sec_8k", "press_release", "transcript"),
        re.compile(
            r"(ad\s+revenue.{0,25}(?:miss|decline|slowdown|worse))"
            r"|(digital\s+ad.{0,30}(?:worse|weak|cut|slowdown))"
            r"|(advertisers?.{0,25}cutting\s+budgets?)",
            re.I,
        ),
        ("ad_revenue", "earnings"),
        "8-K",
        0.85,
    ),
    ExtractionRule(
        "transcript_quote",
        ("transcript",),
        re.compile(r"((?:ceo|cfo|management)\s+(?:said|says|noted|stated).{20,200})", re.I),
        ("transcript", "earnings_call"),
        "earnings_call_transcript",
        0.75,
    ),
    ExtractionRule(
        "analyst_downgrade",
        ("analyst", "news"),
        re.compile(
            r"(downgrad(?:e|ed|es).{0,40}(?:to|from))"
            r"|(cut\s+(?:to|price target).{0,40}(?:neutral|sell|underperform|hold))",
            re.I,
        ),
        ("analyst", "rating"),
        "analyst_note",
        0.75,
    ),
    ExtractionRule(
        "market_move",
        ("market_data", "news"),
        re.compile(
            r"((?:shares?|stock).{0,25}(?:fall|drop|plunge|sink|decline|rise|jump|surge).{0,40}(?:%|percent))"
            r"|((?:after[- ]hours?).{0,30}(?:down|up).{0,20}(?:%|percent))",
            re.I,
        ),
        ("intraday", "volume"),
        "market_data",
        0.8,
        {"direction": 1.0},
    ),
    ExtractionRule(
        "options_vol",
        ("market_data", "news"),
        re.compile(r"((?:put|option|volatility).{0,40}(?:spike|surge|jump|elevated))", re.I),
        ("options", "intraday"),
        "options_flow",
        0.72,
    ),
    ExtractionRule(
        "sector_etf",
        ("market_data", "news"),
        re.compile(
            r"((?:sector|etf|peer|sympathy).{0,40}(?:selloff|decline|fall|drop|compress))",
            re.I,
        ),
        ("sector", "etf"),
        "etf_market",
        0.6,
    ),
    ExtractionRule(
        "short_report",
        ("short_report", "news"),
        re.compile(
            r"(short.{0,15}(?:report|seller).{0,80}(?:fraud|misleading|overstate|fake|fabricat))"
            r"|((?:hindenburg|citron|muddy\s+waters).{0,80}(?:report|research))",
            re.I,
        ),
        ("short", "research"),
        "short_report",
        0.9,
    ),
    ExtractionRule(
        "company_response",
        ("press_release", "news"),
        re.compile(
            r"((?:company|ceo|management)\s+(?:denies|rebut|refute|disputes|responds?).{0,120})",
            re.I,
        ),
        ("response", "company"),
        "press_release",
        0.6,
    ),
    ExtractionRule(
        "regulatory_probe",
        ("news", "sec_filing"),
        re.compile(
            r"((?:sec|doj|ftc|regulator).{0,40}(?:probe|investigation|inquiry|subpoena))",
            re.I,
        ),
        ("regulatory", "sec"),
        "regulatory",
        0.78,
    ),
    ExtractionRule(
        "fomc_statement",
        ("macro", "news"),
        re.compile(
            r"((?:fomc|federal reserve|fed).{0,50}(?:raises?|hike|cut|decision|statement|hawkish))"
            r"|(interest\s+rates?.{0,30}(?:hike|raise|surprise))",
            re.I,
        ),
        ("fomc", "macro"),
        "macro_release",
        0.82,
    ),
    ExtractionRule(
        "cpi_surprise",
        ("macro", "news"),
        re.compile(
            r"((?:cpi|inflation).{0,40}(?:hot|surprise|above|higher than expected))"
            r"|(consumer\s+prices?.{0,30}(?:rise|surge|accelerat))",
            re.I,
        ),
        ("cpi", "macro"),
        "macro_data",
        0.8,
    ),
    ExtractionRule(
        "bond_yield",
        ("macro", "market_data", "news"),
        re.compile(
            r"((?:10[- ]year|treasury|bond)\s+yield.{0,30}(?:jump|surge|rise|spike|climb))"
            r"|(yields?.{0,20}(?:surge|jump).{0,20}bp)",
            re.I,
        ),
        ("bonds", "yields"),
        "bond_market",
        0.75,
    ),
    ExtractionRule(
        "short_squeeze",
        ("news", "social", "market_data"),
        re.compile(
            r"((?:short\s+squeeze|gamma\s+squeeze|covering\s+shorts?).{0,80})"
            r"|((?:melvin|hedge fund).{0,40}cover)",
            re.I,
        ),
        ("short", "social"),
        "market_data",
        0.88,
        {"direction": -1.0},
    ),
    ExtractionRule(
        "social_viral",
        ("news", "social"),
        re.compile(
            r"((?:reddit|stocktwits|twitter|x\.com|trending).{0,60}(?:surge|spike|viral|discussion))"
            r"|((?:meme|viral).{0,40}(?:stock|attention))",
            re.I,
        ),
        ("social", "reddit"),
        "social_media",
        0.72,
    ),
]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 30]


def match_rules(text: str, source_type: str) -> list[tuple[ExtractionRule, re.Match[str]]]:
    hits: list[tuple[ExtractionRule, re.Match[str]]] = []
    for rule in EXTRACTION_RULES:
        if source_type not in rule.source_types and "news" not in rule.source_types:
            continue
        if source_type == "news" or source_type in rule.source_types:
            m = rule.pattern.search(text)
            if m:
                hits.append((rule, m))
    return hits
