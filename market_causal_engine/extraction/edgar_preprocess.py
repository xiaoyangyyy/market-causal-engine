"""Extract earnings-relevant prose from raw SEC EDGAR HTML/plain text."""

from __future__ import annotations

import re

_ITEM_202_PATTERN = re.compile(
    r"item\s+2\.02[\s\S]{0,8000}?(?=item\s+[0-9]|$)",
    re.I,
)
_EXHIBIT_99_PATTERN = re.compile(
    r"exhibit\s+99\.1[\s\S]{0,12000}?(?=exhibit\s+[0-9]|item\s+[0-9]|$)",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    cleaned = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", cleaned).strip()


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z])", text)
    return [p.strip() for p in parts if len(p.strip()) >= 40]


_EARNINGS_KEYWORDS = (
    "revenue",
    "earnings",
    "eps",
    "guidance",
    "outlook",
    "subscriber",
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
    "loss",
    "growth",
    "advertis",
    "dau",
    "users",
)


def _score_paragraph(p: str) -> int:
    lower = p.lower()
    return sum(1 for kw in _EARNINGS_KEYWORDS if kw in lower)


def extract_earnings_sections(text: str, *, max_chars: int = 6000) -> str:
    """Pull Item 2.02 / Exhibit 99.1 and high-signal earnings paragraphs."""
    plain = strip_html(text) if "<" in text else text
    chunks: list[str] = []

    for pattern in (_ITEM_202_PATTERN, _EXHIBIT_99_PATTERN):
        for match in pattern.finditer(plain):
            section = _WS_RE.sub(" ", match.group(0)).strip()
            if len(section) >= 80:
                chunks.append(section)

    if not chunks:
        ranked = sorted(_split_paragraphs(plain), key=_score_paragraph, reverse=True)
        chunks = [p for p in ranked if _score_paragraph(p) >= 2][:12]

    if not chunks:
        return plain[:max_chars]

    merged = "\n\n".join(chunks)
    if len(merged) > max_chars:
        merged = merged[:max_chars].rsplit(" ", 1)[0] + "…"
    return merged


def preprocess_edgar_filing(raw_text: str) -> str:
    """Public entry: normalize EDGAR document text for atom extraction."""
    return extract_earnings_sections(raw_text)
