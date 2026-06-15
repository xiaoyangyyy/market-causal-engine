"""Phase 2 causal claims for catalog EDGAR events."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.catalog.store import (
    atoms_path,
    causal_claims_path,
    load_manifest,
    manifest_path,
    write_manifest,
)
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus
from market_causal_engine.evidence import load_atoms
from market_causal_engine.extraction.causal_claim_extractor import extract_claims_for_atoms
from market_causal_engine.extraction.llm_config import LLMConfig, load_llm_config
from market_causal_engine.lookahead import LookAheadPolicy


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_policy() -> LookAheadPolicy:
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


def load_catalog_claims(event_id: str) -> dict[str, Any] | None:
    path = causal_claims_path(event_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_effective_catalog_claims(
    event_id: str,
    *,
    policy: Any | None = None,
) -> dict[str, Any] | None:
    """Raw claims filtered by quality policy (LLM-only by default when policy set)."""
    from market_causal_engine.benchmark.catalog.claim_quality import (
        apply_catalog_claims_policy,
        load_catalog_claims_policy,
    )

    doc = load_catalog_claims(event_id)
    if doc is None:
        return None
    active = policy if policy is not None else load_catalog_claims_policy()
    if active is None:
        return doc if doc.get("accepted") else None
    return apply_catalog_claims_policy(doc, active)


def has_catalog_claims(event_id: str) -> bool:
    doc = load_catalog_claims(event_id)
    return bool(doc and doc.get("accepted"))


def has_effective_catalog_claims(
    event_id: str,
    *,
    policy: Any | None = None,
) -> bool:
    return load_effective_catalog_claims(event_id, policy=policy) is not None


def extract_claims_for_catalog_event(
    event: BenchmarkEvent,
    *,
    as_of: int = 120,
    use_llm: bool = False,
    llm: LLMConfig | None = None,
    write: bool = True,
) -> dict[str, Any]:
    if not atoms_path(event.event_id).exists():
        raise FileNotFoundError(f"Missing catalog atoms: {event.event_id}")

    atoms = load_atoms(atoms_path(event.event_id))
    domain = str(event.domain or "earnings")
    prefix = event.ticker.upper()[:6] + (event.fiscal_period or "")[:6]
    policy = _default_policy()

    if use_llm:
        from market_causal_engine.benchmark.catalog.llm_claims import extract_catalog_claims_llm

        config = llm or load_llm_config()
        result = extract_catalog_claims_llm(
            atoms,
            domain=domain,
            ticker=event.ticker,
            event_date=event.event_date,
            as_of=as_of,
            policy=policy,
            case_prefix=prefix.replace(" ", "")[:16],
            config=config,
        )
    else:
        result = extract_claims_for_atoms(
            atoms,
            domain=domain,
            as_of=as_of,
            policy=policy,
            use_llm=False,
            case_prefix=prefix.replace(" ", "")[:16],
        )

    out = {
        "event_id": event.event_id,
        "ticker": event.ticker,
        "event_date": event.event_date,
        "domain": domain,
        "as_of": as_of,
        "use_llm": use_llm,
        "computed_at": _utc_now(),
        **result,
    }

    if write:
        path = causal_claims_path(event.event_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out["artifact"] = str(path)

        if manifest_path(event.event_id).exists():
            manifest = load_manifest(event.event_id)
            manifest["causal_claims"] = {
                "claim_count": out["claim_count"],
                "rejected_count": out["rejected_count"],
                "artifact": "causal_claims.json",
            }
            write_manifest(event.event_id, manifest)

    return out


def run_all_catalog_claims(
    *,
    use_llm: bool = False,
    llm: LLMConfig | None = None,
    max_events: int | None = None,
    missing_only: bool = False,
    heuristic_only: bool = False,
    atom_fallback_only: bool = False,
    quality_refresh_only: bool = False,
    benchmark_sample: bool = False,
    llm_delay_sec: float = 0.5,
) -> dict[str, Any]:
    from market_causal_engine.benchmark.catalog.claim_quality import (
        DEFAULT_LLM_QUALITY_POLICY,
        apply_catalog_claims_policy,
        is_heuristic_claims_doc,
        is_llm_claims_doc,
        needs_quality_refresh,
    )
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms, benchmark_sample_event_ids

    config = llm or (load_llm_config() if use_llm else None)
    if use_llm and (config is None or not config.enabled):
        raise RuntimeError("LLM requested but API key not configured")

    events = load_corpus("earnings_sp500_2016_2025", max_events=None)
    events = [e for e in events if not e.metadata.get("synthetic_labels") and _has_usable_atoms(e.event_id)]
    if benchmark_sample:
        sample = benchmark_sample_event_ids(max_events=500, seed=1)
        events = [e for e in events if e.event_id in sample]
    if heuristic_only:
        filtered = []
        for event in events:
            doc = load_catalog_claims(event.event_id)
            if doc and is_heuristic_claims_doc(doc):
                filtered.append(event)
        events = filtered
    elif atom_fallback_only:
        filtered = []
        for event in events:
            doc = load_catalog_claims(event.event_id)
            if doc and is_llm_claims_doc(doc) and doc.get("llm_proposer") == "llm_atom_fallback":
                filtered.append(event)
        events = filtered
    elif quality_refresh_only:
        filtered = []
        for event in events:
            doc = load_catalog_claims(event.event_id)
            if not doc or not doc.get("accepted"):
                continue
            if needs_quality_refresh(doc):
                filtered.append(event)
                continue
            # Offline refine already ran — re-extract quality-eligible llm_event with improved prompt.
            if (
                doc.get("llm_proposer") == "llm_event"
                and apply_catalog_claims_policy(doc, DEFAULT_LLM_QUALITY_POLICY) is not None
            ):
                filtered.append(event)
        events = filtered
    if missing_only:
        events = [e for e in events if not has_catalog_claims(e.event_id)]
    if max_events is not None:
        events = events[:max_events]

    ok: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    llm_events = 0
    for i, event in enumerate(events, start=1):
        try:
            out = extract_claims_for_catalog_event(event, use_llm=use_llm, llm=config)
            ok[event.event_id] = out
            if out.get("llm_proposer"):
                llm_events += 1
            if use_llm and i % 10 == 0:
                print(
                    f"[catalog-claims] {i}/{len(events)} events, claims={sum(v.get('claim_count', 0) for v in ok.values())}",
                    flush=True,
                )
            if use_llm and llm_delay_sec > 0 and i < len(events):
                time.sleep(llm_delay_sec)
        except Exception as exc:  # noqa: BLE001
            errors.append({"event_id": event.event_id, "error": str(exc)})
            if use_llm and i % 10 == 0:
                print(f"[catalog-claims] {i}/{len(events)} ok={len(ok)} err={len(errors)}", flush=True)

    summary = {
        "attempted": len(events),
        "ok": len(ok),
        "errors": errors,
        "total_claims": sum(v.get("claim_count", 0) for v in ok.values()),
        "use_llm": use_llm,
        "heuristic_only": heuristic_only,
        "atom_fallback_only": atom_fallback_only,
        "quality_refresh_only": quality_refresh_only,
        "llm_events": llm_events,
        "llm_model": config.model if config else None,
        "llm_base_url": config.base_url if config else None,
        "computed_at": _utc_now(),
    }
    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "catalog_claims"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "batch_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
