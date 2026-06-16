"""Killer demo payload builder — NFLX 2022 Q1 showcase card."""

from __future__ import annotations

from typing import Any

DEFAULT_DEMO_CASE = "nflx_2022q1_earnings"


def _similar_cases(event_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    from market_causal_engine.case_study import list_case_studies, run_case_study

    cases = list_case_studies()
    by_id = {c["case_id"]: c for c in cases}
    if event_id not in by_id:
        return []
    target = run_case_study(event_id, as_of=120)
    target_path = set(target.get("dominant_causal_path") or target.get("dominant_path") or [])
    target_domain = by_id[event_id].get("domain")
    scored: list[tuple[float, dict[str, Any]]] = []
    for case in cases:
        if case["case_id"] == event_id:
            continue
        r = run_case_study(case["case_id"], as_of=120)
        path = set(r.get("dominant_causal_path") or r.get("dominant_path") or [])
        overlap = len(target_path & path) / max(len(target_path | path), 1)
        domain_bonus = 0.3 if case.get("domain") == target_domain else 0.0
        scored.append((overlap + domain_bonus, case))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, case in scored[:limit]:
        out.append(
            {
                "case_id": case["case_id"],
                "ticker": case.get("ticker"),
                "event_date": case.get("event_date"),
                "domain": case.get("domain"),
                "similarity_score": round(score, 3),
                "description": case.get("description", "")[:120],
            }
        )
    return out


def _timeline_atoms(manifest: dict[str, Any], *, as_of: int) -> list[dict[str, Any]]:
    from pathlib import Path

    from market_causal_engine.evidence import load_atoms
    from market_causal_engine.lookahead import LookAheadPolicy, filter_admissible_atoms
    from market_causal_engine.platform.pit import content_hash
    from market_causal_engine.platform.pit_hardening import CaseTimeAxis, enrich_atom_temporal

    root = Path(manifest["_root"])
    atoms = load_atoms(root / manifest.get("atoms_path", "atoms.jsonl"))
    policy = LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    admissible, _ = filter_admissible_atoms(atoms, as_of=as_of, policy=policy)
    axis = CaseTimeAxis.from_manifest(manifest)
    rows: list[dict[str, Any]] = []
    for atom in sorted(admissible, key=lambda a: (a.effective_time(), a.atom_id)):
        enriched = enrich_atom_temporal(atom, axis)
        temporal = enriched.metadata.get("temporal") or {}
        rows.append(
            {
                "atom_id": atom.atom_id,
                "minute": atom.effective_time(),
                "published_at": atom.published_at,
                "source": atom.source,
                "source_class": atom.metadata.get("source_class"),
                "text": atom.text[:280],
                "tags": atom.tags,
                "published_time_iso": temporal.get("published_time"),
                "source_hash": content_hash({"atom_id": atom.atom_id, "text": atom.text}),
            }
        )
    return rows


def _limitations(result: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    la = result.get("lookahead_audit") or {}
    rejected = int(la.get("rejected_count", 0))
    lines = [
        "Not investment advice — forensic replay for research and audit only.",
        "Observed returns are comparison labels; they never enter the causal kernel at replay time.",
        f"{rejected} post-hoc / look-ahead atoms excluded at this as_of (e.g. next-day analyst, calibration labels).",
        "Macro regime and peer spillovers are approximated; not a full factor model of the tape.",
        "Catalog / scenario router paths differ; headline benchmark uses catalog-only EDGAR path (58.81%, n=840).",
    ]
    if not (result.get("outcome_causal") or {}).get("placebo_rank"):
        lines.append("Placebo rank not computed on fast replay; run with run_placebo=True for full econometric suite.")
    return lines


def build_killer_demo(
    case_id: str = DEFAULT_DEMO_CASE,
    *,
    as_of: int = 120,
) -> dict[str, Any]:
    """Structured demo card: timeline, path, counterfactual, neighbors, confidence, caveats."""
    from market_causal_engine.case_study import load_case_manifest, run_case_study
    from market_causal_engine.counterfactuals.outcome_layer import attach_outcome_causal, build_event_card

    manifest = load_case_manifest(case_id)
    result = run_case_study(case_id, as_of=as_of)
    ev = {"event_id": case_id, **manifest}
    attach_outcome_causal(result, ev, run_placebo=False, car_ablation=True, until=as_of)
    card = build_event_card(result, event=ev)
    oc = result.get("outcome_causal") or {}
    car_ab = oc.get("car_ablation") or {}
    cal = result.get("calibrated_impact") or {}
    obs = manifest.get("observed_outcomes") or {}
    mech = result.get("mechanism_contributions") or {}

    path_labels = {
        "earnings_miss": "subscriber / earnings miss",
        "guidance_cut": "guidance reduction → forward revision",
        "analyst_downgrade": "sell-side downgrade cascade",
        "growth_repricing": "growth multiple compression",
        "liquidity_stress": "liquidity / vol channel",
        "fundamental": "fundamental repricing",
        "sentiment": "sentiment / narrative",
    }
    raw_path = result.get("dominant_causal_path") or result.get("dominant_path") or []
    narrative_path = [path_labels.get(p, p.replace("_", " ")) for p in raw_path]

    return {
        "demo_id": f"killer_{case_id}",
        "case_id": case_id,
        "as_of_minutes": as_of,
        "hero": {
            "title": f"{manifest.get('ticker')} — {manifest.get('description', case_id)}",
            "ticker": manifest.get("ticker"),
            "event_date": manifest.get("event_date"),
            "domain": manifest.get("domain", "earnings"),
            "tagline": "Point-in-time event forensics: path + econometric counterfactual",
        },
        "event_timeline": _timeline_atoms(manifest, as_of=as_of),
        "mechanism_path": {
            "steps": raw_path,
            "narrative": narrative_path,
            "dominant_path": raw_path,
            "mechanism_contributions": mech,
        },
        "counterfactual": {
            "outcome_causal": oc,
            "event_study": oc.get("event_study"),
            "car_ablation": car_ab,
            "observed": {
                "direction": obs.get("direction"),
                "after_hours_return_pct": obs.get("after_hours_return_pct"),
                "two_day_return_pct": obs.get("two_day_return_pct"),
            },
            "model": {
                "simulated_direction": result.get("simulated_direction"),
                "estimated_after_hours_return_pct": cal.get("estimated_after_hours_return_pct"),
                "after_hours_error_pct": cal.get("after_hours_error_pct"),
            },
        },
        "channel_ablation": car_ab.get("channels") or {},
        "dominant_channel": car_ab.get("dominant_channel"),
        "benchmark_neighbors": _similar_cases(case_id),
        "confidence": {
            "path_attribution": result.get("path_attribution"),
            "drawdown_risk": (result.get("final_risk") or {}).get("drawdown_risk"),
            "directional_pressure": (result.get("final_risk") or {}).get("directional_pressure"),
            "direction_match": (result.get("case_study") or {}).get("direction_match"),
            "pit_audit_passed": (result.get("pit_audit") or {}).get("passed"),
            "lookahead_rejected": (result.get("lookahead_audit") or {}).get("rejected_count"),
        },
        "audits": {
            "lookahead_audit": result.get("lookahead_audit"),
            "pit_audit": result.get("pit_audit"),
        },
        "limitations": _limitations(result, manifest),
        "event_card": card,
    }
