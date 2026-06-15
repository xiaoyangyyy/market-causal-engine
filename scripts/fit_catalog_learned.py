"""Fit Phase 4 catalog domain model + learned router."""

from __future__ import annotations

import argparse
import json
import sys

from market_causal_engine.benchmark.catalog.claim_quality import CatalogClaimsPolicy
from market_causal_engine.benchmark.catalog.fit_learned import fit_catalog_learned_stack
from market_causal_engine.learned.store import reload_learned_store


def _build_policy(args: argparse.Namespace) -> CatalogClaimsPolicy | None:
    if args.all_claims:
        return None
    return CatalogClaimsPolicy(
        llm_only=not args.allow_heuristic,
        min_accepted_claims=args.min_claims,
        min_claim_confidence=args.min_claim_confidence,
        min_claim_polarity=args.min_claim_polarity,
        min_claim_severity=args.min_claim_severity,
        min_net_polarity=args.min_net_polarity,
        exclude_boilerplate=not args.keep_boilerplate,
        exclude_atom_fallback=not args.allow_atom_fallback,
        max_claims_per_event=args.max_claims or 4,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit catalog domain model and router (Phase 4)")
    parser.add_argument("--max-events", type=int, default=0, help="Limit training events (0 = all)")
    parser.add_argument("--min-domain-samples", type=int, default=40)
    parser.add_argument("--min-router-samples", type=int, default=40)
    parser.add_argument("--all-claims", action="store_true", help="Train on all raw claims (legacy)")
    parser.add_argument("--allow-heuristic", action="store_true", help="Include heuristic claim events")
    parser.add_argument("--min-claims", type=int, default=2, help="Min accepted claims per event")
    parser.add_argument("--min-claim-confidence", type=float, default=0.50)
    parser.add_argument("--min-claim-polarity", type=float, default=0.10)
    parser.add_argument("--min-claim-severity", type=float, default=0.0)
    parser.add_argument("--min-net-polarity", type=float, default=0.08)
    parser.add_argument("--allow-atom-fallback", action="store_true", help="Allow llm_atom_fallback events")
    parser.add_argument("--keep-boilerplate", action="store_true")
    parser.add_argument("--max-claims", type=int, default=4, help="Cap claims per event (0 = no cap)")
    parser.add_argument("--direction-balance-classes", action="store_true")
    parser.add_argument("--direction-ridge", type=float, default=0.3)
    args = parser.parse_args()

    policy = _build_policy(args)
    summary = fit_catalog_learned_stack(
        max_events=args.max_events or None,
        min_domain_samples=args.min_domain_samples,
        min_router_samples=args.min_router_samples,
        claims_policy=policy,
        use_llm_quality_policy=not args.all_claims,
        direction_balance_classes=args.direction_balance_classes,
        direction_ridge=args.direction_ridge,
    )
    reload_learned_store()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
