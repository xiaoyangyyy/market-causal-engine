"""Phase 4: fit catalog domain model + router from claims and replay."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.catalog.claims import has_catalog_claims, has_effective_catalog_claims
from market_causal_engine.benchmark.catalog.claim_quality import (
    CatalogClaimsPolicy,
    DEFAULT_LLM_QUALITY_POLICY,
    save_catalog_claims_policy,
)
from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
from market_causal_engine.benchmark.catalog.replay import replay_catalog_feed_event
from market_causal_engine.benchmark.catalog.direction_model import (
    CatalogDirectionModel,
    collect_direction_samples,
    save_catalog_direction_model,
)
from market_causal_engine.benchmark.catalog.router import (
    CatalogRouterModel,
    attach_predicted_effect,
    build_router_features,
    save_catalog_router,
)
from market_causal_engine.benchmark.models import BenchmarkEvent, load_corpus
from market_causal_engine.benchmark.replay import infer_simulated_direction, replay_scenario_event
from market_causal_engine.calibration.domain_models import save_domain_models
from market_causal_engine.calibration.mechanism_model import MechanismModel, TrainingSample
from market_causal_engine.learned.features import build_inference_features

LEARNED_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "market" / "learned"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _direction_match(observed: str, simulated: str | None) -> bool:
    if simulated is None:
        return False
    if observed == "neutral":
        return simulated == "neutral"
    return observed == simulated


DIRECTION_EFFECT = {"up": 1.0, "down": -1.0, "neutral": 0.0}


def _training_effect(event: BenchmarkEvent) -> float | None:
    """Phase 1 abnormal return as regression target for catalog mechanism model."""
    oc = event.outcome_causal or {}
    if "effect" in oc:
        return float(oc["effect"])
    return None


def collect_catalog_domain_samples(
    events: list[BenchmarkEvent] | None = None,
    *,
    max_events: int | None = None,
    claims_policy: CatalogClaimsPolicy | None = None,
) -> list[TrainingSample]:
    if events is None:
        events = load_corpus("earnings_sp500_2016_2025", max_events=None)

    samples: list[TrainingSample] = []
    for event in events:
        if event.metadata.get("synthetic_labels"):
            continue
        if not _has_usable_atoms(event.event_id):
            continue
        if claims_policy is not None:
            if not has_effective_catalog_claims(event.event_id, policy=claims_policy):
                continue
        elif not has_catalog_claims(event.event_id):
            continue
        target = _training_effect(event)
        if target is None:
            continue
        try:
            result = replay_catalog_feed_event(event, until=60, claims_policy=claims_policy)
            feats = build_inference_features(result, event.to_dict(), domain="earnings", with_earnings_interactions=True)
            samples.append(
                TrainingSample(
                    event_id=event.event_id,
                    features=feats,
                    effect=target,
                    domain="earnings",
                    source="catalog_feed",
                )
            )
        except Exception:  # noqa: BLE001
            continue
        if max_events is not None and len(samples) >= max_events:
            break
    return samples


def collect_router_samples(
    events: list[BenchmarkEvent] | None = None,
    *,
    model: MechanismModel | None = None,
    max_events: int | None = None,
    claims_policy: CatalogClaimsPolicy | None = None,
) -> list[TrainingSample]:
    if events is None:
        events = load_corpus("earnings_sp500_2016_2025", max_events=None)

    samples: list[TrainingSample] = []
    for event in events:
        if event.metadata.get("synthetic_labels"):
            continue
        if not _has_usable_atoms(event.event_id):
            continue
        if claims_policy is not None:
            if not has_effective_catalog_claims(event.event_id, policy=claims_policy):
                continue
        elif not has_catalog_claims(event.event_id):
            continue
        obs = event.observed_outcomes.get("direction")
        if obs not in ("up", "down", "neutral"):
            continue
        try:
            ev_dict = event.to_dict()
            cat = replay_catalog_feed_event(event, until=60, claims_policy=claims_policy)
            scen = replay_scenario_event(event, until=60)
            if model is not None:
                attach_predicted_effect(cat, ev_dict, model)
                attach_predicted_effect(scen, ev_dict, model)
            cat_dir = infer_simulated_direction(cat, event=ev_dict)
            scen_dir = infer_simulated_direction(scen, event=ev_dict)
            cat_ok = _direction_match(str(obs), cat_dir)
            scen_ok = _direction_match(str(obs), scen_dir)
            # Prefer catalog only when it wins and scenario does not (scenario is safe default).
            label = 1.0 if cat_ok and not scen_ok else 0.0
            feats = build_router_features(cat, scen, event=ev_dict)
            samples.append(
                TrainingSample(
                    event_id=event.event_id,
                    features=feats,
                    effect=label,
                    domain="earnings",
                    source="router",
                )
            )
        except Exception:  # noqa: BLE001
            continue
        if max_events is not None and len(samples) >= max_events:
            break
    return samples


def fit_catalog_learned_stack(
    *,
    max_events: int | None = None,
    min_domain_samples: int = 40,
    min_router_samples: int = 40,
    claims_policy: CatalogClaimsPolicy | None = None,
    use_llm_quality_policy: bool = True,
    direction_balance_classes: bool = False,
    direction_ridge: float = 0.3,
) -> dict[str, Any]:
    from market_causal_engine.calibration.feature_builder import EARNINGS_FEATURE_ORDER

    LEARNED_DIR.mkdir(parents=True, exist_ok=True)
    active_policy: CatalogClaimsPolicy | None
    if use_llm_quality_policy:
        active_policy = claims_policy or DEFAULT_LLM_QUALITY_POLICY
        policy_path = save_catalog_claims_policy(active_policy, LEARNED_DIR / "catalog_claims_policy.json")
    else:
        active_policy = None
        policy_path = None

    domain_samples = collect_catalog_domain_samples(
        max_events=max_events,
        claims_policy=active_policy,
    )
    if len(domain_samples) < min_domain_samples:
        raise ValueError(f"Need >= {min_domain_samples} catalog domain samples, got {len(domain_samples)}")

    catalog_model = MechanismModel(feature_names=list(EARNINGS_FEATURE_ORDER)).fit(domain_samples)
    catalog_path = LEARNED_DIR / "catalog_domain_model.json"
    save_domain_models({"catalog_earnings": catalog_model}, catalog_path)

    events = load_corpus("earnings_sp500_2016_2025", max_events=None)
    direction_samples = collect_direction_samples(
        events,
        domain_model=catalog_model,
        max_events=max_events,
        claims_policy=active_policy,
    )
    direction_model: CatalogDirectionModel | None = None
    direction_path = LEARNED_DIR / "catalog_direction_model.json"
    if len(direction_samples) >= 40:
        direction_model = CatalogDirectionModel().fit(
            direction_samples,
            ridge=direction_ridge,
            balance_classes=direction_balance_classes,
        )
        save_catalog_direction_model(direction_model, direction_path)

    from market_causal_engine.learned.store import reload_learned_store

    reload_learned_store()
    router_samples = collect_router_samples(
        model=catalog_model,
        max_events=max_events,
        claims_policy=active_policy,
    )
    router: CatalogRouterModel | None = None
    router_path = LEARNED_DIR / "catalog_router.json"
    if len(router_samples) >= min_router_samples:
        router = CatalogRouterModel().fit(router_samples)
        save_catalog_router(router, router_path)

    summary = {
        "computed_at": _utc_now(),
        "catalog_claims_policy": active_policy.to_dict() if active_policy else None,
        "catalog_domain_samples": len(domain_samples),
        "catalog_domain_rmse": catalog_model.training_rmse,
        "catalog_direction_samples": len(direction_samples),
        "catalog_direction_train_accuracy": direction_model.training_accuracy if direction_model else None,
        "catalog_direction_holdout_accuracy": direction_model.holdout_accuracy if direction_model else None,
        "catalog_direction_confidence_margin": direction_model.confidence_margin if direction_model else None,
        "router_samples": len(router_samples),
        "router_training_accuracy": router.training_accuracy if router else None,
        "artifacts": {
            "catalog_claims_policy": str(policy_path) if policy_path else None,
            "catalog_domain_model": str(catalog_path),
            "catalog_direction_model": str(direction_path) if direction_model else None,
            "catalog_router": str(router_path) if router else None,
        },
    }
    (LEARNED_DIR / "catalog_fit_summary.json").write_text(
        __import__("json").dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary
