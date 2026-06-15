"""Load persisted learned artifacts (replaces static heuristics)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from market_causal_engine.calibration.domain_models import load_domain_models, load_earnings_magnitude_model
from market_causal_engine.calibration.mechanism_model import MechanismModel
from market_causal_engine.benchmark.catalog.router import load_catalog_router
from market_causal_engine.benchmark.catalog.direction_model import load_catalog_direction_model
from market_causal_engine.benchmark.catalog.claim_quality import load_catalog_claims_policy

LEARNED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "learned"


def _read_json(name: str, default: Any) -> Any:
    path = LEARNED_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_learned_store() -> dict[str, Any]:
    domain_raw = _read_json("domain_models.json", {})
    domain_models: dict[str, MechanismModel] = {}
    for domain, payload in domain_raw.get("models", {}).items():
        domain_models[domain] = MechanismModel.from_dict(payload)

    earnings_mag = load_earnings_magnitude_model(LEARNED_DIR / "earnings_magnitude.json")

    catalog_domain_model: MechanismModel | None = None
    catalog_model_path = LEARNED_DIR / "catalog_domain_model.json"
    if catalog_model_path.exists():
        loaded = load_domain_models(catalog_model_path)
        catalog_domain_model = loaded.get("catalog_earnings") or next(iter(loaded.values()), None)

    catalog_router = load_catalog_router()
    catalog_direction_model = load_catalog_direction_model()
    catalog_claims_policy = load_catalog_claims_policy()

    return {
        "version": domain_raw.get("version", "v0.9-earnings-interaction"),
        "kind_scales": _read_json("kind_scales.json", {}).get("scales", {}),
        "severity_table": _read_json("severity_table.json", {}).get("by_kind", {}),
        "rule_weights": _read_json("compiler_weights.json", {}).get("weights", {}),
        "category_map": _read_json("category_map.json", {}).get("map", {}),
        "domain_posteriors": _read_json("domain_posteriors.json", {}).get("domains", {}),
        "domain_models": domain_models,
        "catalog_domain_model": catalog_domain_model,
        "catalog_direction_model": catalog_direction_model,
        "catalog_router": catalog_router,
        "catalog_claims_policy": catalog_claims_policy,
        "earnings_magnitude_model": earnings_mag or domain_models.get("earnings"),
        "path_attention": float(_read_json("path_attention.json", {}).get("on_path", 0.65)),
    }


def learned_available() -> bool:
    return (LEARNED_DIR / "domain_models.json").exists()


def reload_learned_store() -> dict[str, Any]:
    load_learned_store.cache_clear()
    return load_learned_store()
