"""Score compiler rules instead of first-match keyword heuristics."""

from __future__ import annotations

from market_causal_engine.compiler import CompilerRule
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.learned.severity import estimate_severity
from market_causal_engine.learned.store import load_learned_store


def score_rule(rule: CompilerRule, atom: MarketAtom, *, domain: str = "earnings") -> float:
    store = load_learned_store()
    text_lower = atom.text.lower()

    if atom.metadata.get("catalog_boilerplate"):
        if rule.event_kind in ("guidance_cut", "analyst_downgrade", "short_seller_report"):
            return 0.0

    tag_match = not rule.match_tags or any(t in atom.tags for t in rule.match_tags)
    if not tag_match:
        return 0.0

    kw_score = 0.0
    if rule.match_keywords:
        hits = sum(1 for kw in rule.match_keywords if kw in text_lower)
        if hits == 0:
            return 0.0
        kw_score = min(1.0, hits / max(1, len(rule.match_keywords)))

    base = float(store.get("rule_weights", {}).get(rule.rule_id, 0.55))
    meta_boost = float(atom.metadata.get("severity", 0.0)) * 0.25
    confidence = float(atom.metadata.get("confidence", 0.5)) * 0.15
    sev = estimate_severity(atom, event_kind=rule.event_kind, domain=domain) * 0.2
    score = round(base * 0.45 + kw_score * 0.35 + meta_boost + confidence + sev, 4)

    if atom.metadata.get("extracted_by") == "financial_results":
        if rule.event_kind == "earnings_release":
            score += 0.28
        elif rule.event_kind == "guidance_cut":
            score *= 0.25

    polarity = float(atom.metadata.get("catalog_polarity", 0.0))
    if polarity > 0 and rule.event_kind == "earnings_release":
        score += 0.08
    if polarity < 0 and rule.event_kind in ("guidance_cut", "earnings_release"):
        score += 0.05

    return score


def select_best_rule(rules: list[CompilerRule], atom: MarketAtom, *, domain: str = "earnings") -> tuple[CompilerRule | None, float]:
    best: CompilerRule | None = None
    best_score = 0.0
    for rule in rules:
        score = score_rule(rule, atom, domain=domain)
        if score > best_score:
            best_score = score
            best = rule
    if best is None or best_score < 0.15:
        return None, 0.0
    return best, best_score
