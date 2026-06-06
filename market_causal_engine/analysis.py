"""Forensic analysis: path-weighted attribution and domain-specific outputs."""

from __future__ import annotations

from typing import Any

from market_causal_engine.constants import DOMAIN_REGISTRY, OUTCOME_KEYS, SCENARIO_DOMAIN

MECHANISM_CATEGORIES: dict[str, str] = {
    "earnings_release": "fundamental",
    "earnings_miss": "fundamental",
    "earnings_beat": "fundamental",
    "earnings_call_transcript": "fundamental",
    "guidance_cut": "fundamental",
    "guidance_raise": "fundamental",
    "margin_pressure": "fundamental",
    "ad_revenue_miss": "fundamental",
    "digital_ad_slowdown": "macro",
    "macro_ad_budget_cut": "macro",
    "analyst_downgrade": "sentiment",
    "analyst_upgrade": "sentiment",
    "analyst_rating_change": "sentiment",
    "institutional_rebalance": "liquidity",
    "liquidity_dry_up": "liquidity",
    "large_sell_order": "liquidity",
    "price_impact_amplified": "liquidity",
    "intraday_volume_spike": "liquidity",
    "intraday_volatility_spike": "liquidity",
    "put_volume_spike": "liquidity",
    "option_gamma_pressure": "liquidity",
    "sector_etf_movement": "fundamental",
    "viral_negative_news": "sentiment",
    "retail_attention_spike": "sentiment",
    "news_amplification": "sentiment",
    "social_discussion_spike": "sentiment",
    "short_seller_report": "sentiment",
    "company_response": "fundamental",
    "trust_erosion": "sentiment",
    "regulatory_probe": "regulatory",
    "short_cover_risk": "liquidity",
    "continuation_pressure": "sentiment",
    "reversal_signal": "sentiment",
    "macro_rate_shock": "macro",
    "fomc_statement": "macro",
    "cpi_surprise": "macro",
    "nfp_surprise": "macro",
    "bond_yield_reaction": "macro",
    "growth_value_rotation": "macro",
    "sector_spillover": "macro",
    "beta_transmission": "macro",
    "company_clarification": "intervention",
    "buyback_announcement": "intervention",
    "liquidity_support": "intervention",
    "suppress_analyst_downgrade": "intervention",
}


def _kinds_on_dominant_path(trace: list[dict[str, Any]], dominant_path: list[str]) -> set[str]:
    if not dominant_path:
        return {e.get("kind", "") for e in trace if e.get("action") == "executed"}
    path_set = set(dominant_path)
    expanded = set(path_set)
    for entry in trace:
        if entry.get("action") != "executed":
            continue
        kind = entry.get("kind", "")
        if kind in path_set:
            for cause in entry.get("cause", []):
                if cause.startswith("event:"):
                    parent_id = cause.split(":", 1)[1]
                    for parent in trace:
                        if parent.get("event_id") == parent_id and parent.get("kind"):
                            expanded.add(parent["kind"])
    return expanded


def compute_mechanism_contributions(
    trace: list[dict[str, Any]],
    *,
    dominant_path: list[str] | None = None,
    path_weighted: bool = True,
) -> dict[str, Any]:
    """Attribute outcome deltas; path-weighted mode down-weights off-path amplification."""
    dominant_path = dominant_path or []
    on_path = _kinds_on_dominant_path(trace, dominant_path)

    buckets: dict[str, float] = {
        "fundamental": 0.0,
        "sentiment": 0.0,
        "liquidity": 0.0,
        "macro": 0.0,
        "regulatory": 0.0,
    }
    by_mechanism: dict[str, float] = {}

    for entry in trace:
        if entry.get("action") != "commit":
            continue
        kind = entry.get("kind", "")
        category = MECHANISM_CATEGORIES.get(kind)
        if not category or category == "intervention":
            continue
        patch = entry.get("patch", {})
        delta = sum(max(0.0, float(patch.get(k, 0.0))) for k in OUTCOME_KEYS)
        weight = 1.0 if not path_weighted else (1.0 if kind in on_path else 0.35)
        weighted = delta * weight
        buckets[category] += weighted
        by_mechanism[kind] = by_mechanism.get(kind, 0.0) + weighted

    total = sum(buckets.values()) or 1.0
    shares = {k: round(v / total, 4) for k, v in buckets.items()}
    shares["raw"] = {k: round(v, 4) for k, v in buckets.items()}
    dominant_key = max(buckets, key=lambda k: buckets[k]) if any(buckets.values()) else "mixed"
    shares["dominant_bucket"] = dominant_key if buckets.get(dominant_key, 0) > 0 else "mixed"
    shares["by_mechanism"] = {k: round(v / total, 4) for k, v in sorted(by_mechanism.items(), key=lambda x: -x[1])[:8]}
    shares["path_weighted"] = path_weighted
    return shares


def _impact_direction(final_risk: dict[str, float]) -> str:
    pressure = final_risk.get("directional_pressure", 0.0)
    if pressure >= 0.12:
        return "down"
    if pressure <= -0.05:
        return "up"
    return "neutral"


def _dominant_decline_or_rise_reason(contributions: dict[str, Any], dominant_path: list[str]) -> str:
    bucket = contributions.get("dominant_bucket", "mixed")
    if dominant_path:
        head = " -> ".join(dominant_path[:5])
        return f"{bucket}_via_{dominant_path[0]} ({head})"
    return f"{bucket}_mechanisms"


def build_earnings_output(result: dict[str, Any]) -> dict[str, Any]:
    path = result.get("dominant_causal_path", [])
    contributions = compute_mechanism_contributions(result.get("trace", []), dominant_path=path)
    risk = result.get("final_risk", {})
    return {
        "earnings_impact_path": path,
        "dominant_move_reason": _dominant_decline_or_rise_reason(contributions, path),
        "move_direction": _impact_direction(risk),
        "mechanism_contributions": {
            "fundamental": contributions["fundamental"],
            "sentiment": contributions["sentiment"],
            "liquidity": contributions["liquidity"],
        },
        "mechanism_detail": contributions.get("by_mechanism", {}),
        "dominant_contribution_bucket": contributions["dominant_bucket"],
        "interpretation": _earnings_interpretation(contributions, path, risk),
    }


def _earnings_interpretation(contributions: dict[str, Any], path: list[str], risk: dict[str, float]) -> str:
    parts: list[str] = []
    if "guidance_cut" in path:
        parts.append("guidance_cut on causal path")
    elif "ad_revenue_miss" in path:
        parts.append("ad_revenue_miss on causal path")
    elif "earnings_miss" in path:
        parts.append("earnings_miss on causal path")
    parts.append(f"dominant bucket: {contributions.get('dominant_bucket')}")
    if risk.get("drawdown_risk", 0) > 0.2:
        parts.append(f"drawdown_risk={round(risk.get('drawdown_risk', 0), 3)}")
    return "; ".join(parts)


def build_short_report_output(result: dict[str, Any]) -> dict[str, Any]:
    path = result.get("dominant_causal_path", [])
    contributions = compute_mechanism_contributions(result.get("trace", []), dominant_path=path)
    state = result.get("final_state", {})
    risk = result.get("final_risk", {})
    reversal_prob = _estimate_reversal_probability(state, risk, path)
    return {
        "trust_impact_path": path,
        "trust_level_final": round(state.get("trust_level", 0.5), 4),
        "liquidity_pressure": risk.get("liquidity_stress", 0.0),
        "regulatory_risk": round(state.get("regulatory_risk", 0.0), 4),
        "mechanism_contributions": {
            "sentiment": contributions["sentiment"],
            "liquidity": contributions["liquidity"],
            "regulatory": contributions["regulatory"],
            "fundamental": contributions["fundamental"],
        },
        "continuation_vs_reversal": {
            "reversal_probability": reversal_prob,
            "likely_mechanism": "short_cover_squeeze" if reversal_prob > 0.55 else "continued_pressure",
            "explanation": _short_continuation_explanation(path, state, risk, reversal_prob),
        },
    }


def _estimate_reversal_probability(state: dict[str, float], risk: dict[str, float], path: list[str]) -> float:
    score = 0.2
    if state.get("short_interest_pressure", 0) > 0.5:
        score += 0.2
    if "company_response" in path and state.get("trust_level", 0.5) > 0.45:
        score += 0.25
    if risk.get("liquidity_stress", 0) > 0.35:
        score += 0.15
    if "reversal_signal" in path:
        score += 0.2
    if "regulatory_probe" in path:
        score -= 0.15
    return round(min(0.95, max(0.05, score)), 4)


def _short_continuation_explanation(path, state, risk, reversal_prob) -> str:
    if reversal_prob > 0.55:
        return "High short interest + partial trust recovery favors squeeze/reversal path"
    if "regulatory_probe" in path:
        return "Regulatory overhang keeps pressure; reversal less likely without clearance"
    if risk.get("liquidity_stress", 0) > 0.3:
        return "Liquidity stress dominates; continuation via forced selling more likely"
    return "Trust erosion and news amplification sustain downward path"


def build_macro_output(result: dict[str, Any]) -> dict[str, Any]:
    path = result.get("dominant_causal_path", [])
    contributions = compute_mechanism_contributions(result.get("trace", []), dominant_path=path)
    state = result.get("final_state", {})
    return {
        "macro_transmission_path": path,
        "macro_to_sector_to_stock": _extract_transmission_chain(path),
        "mechanism_contributions": {
            "macro": contributions["macro"],
            "fundamental": contributions["fundamental"],
            "liquidity": contributions["liquidity"],
        },
        "bond_yield_pressure": round(state.get("bond_yield_pressure", 0.0), 4),
        "growth_value_tilt": round(state.get("growth_value_tilt", 0.0), 4),
        "stock_beta_exposure": round(state.get("stock_beta_exposure", 0.0), 4),
        "interpretation": _macro_interpretation(path, state),
    }


def _extract_transmission_chain(path: list[str]) -> list[str]:
    macro_kinds = {"fomc_statement", "cpi_surprise", "nfp_surprise", "macro_rate_shock", "bond_yield_reaction", "macro_ad_budget_cut"}
    sector_kinds = {"sector_spillover", "sector_etf_movement", "growth_value_rotation", "digital_ad_slowdown"}
    stock_kinds = {"beta_transmission", "price_impact_amplified", "institutional_rebalance"}
    chain: list[str] = []
    for group, kinds in [("macro_shock", macro_kinds), ("sector_channel", sector_kinds), ("stock_impact", stock_kinds)]:
        for kind in path:
            if kind in kinds and group not in chain:
                chain.append(group)
                break
    return chain or ["direct_macro_impact"]


def _macro_interpretation(path: list[str], state: dict[str, float]) -> str:
    parts: list[str] = []
    if "bond_yield_reaction" in path:
        parts.append("bond yield channel active")
    if "digital_ad_slowdown" in path or "macro_ad_budget_cut" in path:
        parts.append("ad-cycle macro channel active")
    if "beta_transmission" in path:
        parts.append("high-beta stock amplified macro move")
    return "; ".join(parts) if parts else "macro shock transmitted via sector spillover"


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    scenario_id = result.get("scenario_id", "")
    domain = SCENARIO_DOMAIN.get(scenario_id) or _guess_domain(scenario_id)
    result["domain"] = domain
    result["mvp"] = domain  # backward compat

    path = result.get("dominant_causal_path", [])
    if domain == "earnings":
        result["forensic_output"] = build_earnings_output(result)
    elif domain == "short_report":
        result["forensic_output"] = build_short_report_output(result)
    elif domain == "macro":
        result["forensic_output"] = build_macro_output(result)
    else:
        result["forensic_output"] = {
            "dominant_causal_path": path,
            "mechanism_contributions": compute_mechanism_contributions(
                result.get("trace", []), dominant_path=path
            ),
        }
    result["mvp_output"] = result["forensic_output"]  # backward compat
    result["mechanism_contributions"] = compute_mechanism_contributions(
        result.get("trace", []), dominant_path=path
    )
    return result


def _guess_domain(scenario_id: str) -> str:
    sid = scenario_id.lower()
    if "earnings" in sid or sid.startswith("e") or sid.startswith("case_n") or sid.startswith("case_s"):
        if "short" in sid:
            return "short_report"
        return "earnings"
    if "short" in sid or sid.startswith("s"):
        return "short_report"
    if "macro" in sid or "fed" in sid or "cpi" in sid or sid.startswith("x"):
        return "macro"
    return "general"


# Backward compat exports
MVP_GROUPS = DOMAIN_REGISTRY
SCENARIO_MVP = SCENARIO_DOMAIN
