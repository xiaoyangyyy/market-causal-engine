"""Feed-only kernel replay for catalog events with per-ticker EDGAR atoms."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from market_causal_engine.analysis import enrich_result
from market_causal_engine.benchmark.catalog.claims import load_catalog_claims, load_effective_catalog_claims
from market_causal_engine.benchmark.catalog.claim_quality import CatalogClaimsPolicy
from market_causal_engine.benchmark.catalog.store import atoms_path, load_manifest
from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.replay import filter_atoms_by_channel, infer_simulated_direction
from market_causal_engine.calibration import attach_calibration
from market_causal_engine.config import KernelConfig
from market_causal_engine.evidence import load_atoms
from market_causal_engine.feed import FeedRunner
from market_causal_engine.lookahead import LookAheadPolicy, filter_admissible_atoms
from market_causal_engine.reverse import analyze_result, infer_market_regime
from market_causal_engine.scenarios import build_kernel, inject_interventions, load_intervention, load_scenario


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _base_scenario_path() -> Path:
    return _project_root() / "data" / "market" / "scenarios" / "catalog_feed_base.json"


def _default_lookahead_policy() -> LookAheadPolicy:
    return LookAheadPolicy(
        strict=True,
        forbid_post_hoc_sources=True,
        forbidden_source_classes=(
            "post_mortem",
            "next_day_only",
            "calibration_label",
            "future_analyst",
        ),
    )


def has_catalog_atoms(event_id: str) -> bool:
    path = atoms_path(event_id)
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        manifest = load_manifest(event_id)
        return int(manifest.get("atom_count", 0)) > 0
    except FileNotFoundError:
        return path.stat().st_size > 0


def replay_catalog_feed_event(
    event: BenchmarkEvent,
    *,
    until: int = 120,
    world_id: str = "W0",
    atom_filter: str | None = None,
    claims_policy: CatalogClaimsPolicy | None = ...,
) -> dict[str, Any]:
    """Replay catalog event: atoms → kernel; direction from Phase 4 learned model + causal claims."""
    manifest = load_manifest(event.event_id)
    all_atoms = load_atoms(atoms_path(event.event_id))
    if atom_filter:
        all_atoms = filter_atoms_by_channel(all_atoms, atom_filter)

    policy = _default_lookahead_policy()
    admissible, lookahead_report = filter_admissible_atoms(all_atoms, as_of=until, policy=policy)

    scenario = load_scenario(_base_scenario_path())
    scenario = {
        **scenario,
        "scenario_id": f"catalog_{event.event_id}",
        "description": f"Catalog feed replay: {event.ticker} {event.event_date}",
    }

    domain = str(event.domain or "earnings")
    config = KernelConfig.full()
    kernel = build_kernel(scenario, world_id, domain=domain)
    if config.use_interventions:
        inject_interventions(kernel, load_intervention(world_id))

    runner = FeedRunner(
        kernel,
        ticker=event.ticker,
        skip_evidence_ledger=not config.use_evidence_ledger,
        lookahead_policy=policy,
        as_of=until,
        domain=domain,
    )
    runner.run_atoms(admissible, until=until)

    result = kernel.to_result(scenario_id=scenario["scenario_id"], world_id=world_id)
    debugger = analyze_result(result)
    result["dominant_causal_path"] = debugger.dominant_causal_path()
    result["dominant_risk_path"] = result["dominant_causal_path"]

    if claims_policy is ...:
        claims_doc = load_effective_catalog_claims(event.event_id)
    elif claims_policy is None:
        claims_doc = load_catalog_claims(event.event_id)
        if claims_doc and not claims_doc.get("accepted"):
            claims_doc = None
    else:
        claims_doc = load_effective_catalog_claims(event.event_id, policy=claims_policy)
    if claims_doc and claims_doc.get("accepted"):
        result["causal_claims"] = {
            "accepted": claims_doc["accepted"],
            "rejected": claims_doc.get("rejected", []),
            "llm_proposer": claims_doc.get("llm_proposer"),
            "catalog_net_polarity": claims_doc.get("catalog_net_polarity"),
            "catalog_quality_score": claims_doc.get("catalog_quality_score"),
        }

    enrich_result(result)
    result["market_regime"] = infer_market_regime(result["final_state"])
    result["lookahead_audit"] = lookahead_report.to_dict()
    result["catalog_manifest"] = manifest
    result["catalog_atom_count"] = len(all_atoms)
    result["catalog_admissible_count"] = len(admissible)
    result["catalog_claim_count"] = len((claims_doc or {}).get("accepted", []))

    attach_calibration(result, event.observed_outcomes)
    aligned = manifest.get("aligned_observed_outcomes")
    if aligned:
        result["aligned_observed_outcomes"] = aligned
        result["aligned_filing_date"] = manifest.get("aligned_filing_date")
        result["observed_direction"] = aligned.get("direction")
    else:
        result["observed_direction"] = event.observed_outcomes.get("direction")

    result["benchmark_event_id"] = event.event_id
    result["replay_mode"] = "catalog_feed" if not atom_filter else f"catalog_feed:{atom_filter}"
    result["domain"] = domain
    result["simulated_direction"] = infer_simulated_direction(result, event=event.to_dict())
    return result
