"""Offline refinement of stored catalog causal claims (no LLM API)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refine stored catalog claims (polarity + generic effects)")
    parser.add_argument("--max-events", type=int, default=0, help="Limit events (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing files")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from market_causal_engine.benchmark.catalog.claim_quality import (
        apply_catalog_claims_policy,
        needs_quality_refresh,
        refine_stored_claims_doc,
    )
    from market_causal_engine.benchmark.catalog.claims import load_catalog_claims
    from market_causal_engine.benchmark.catalog.queue import _has_usable_atoms
    from market_causal_engine.benchmark.catalog.store import causal_claims_path
    from market_causal_engine.benchmark.models import load_corpus

    events = [
        e
        for e in load_corpus("earnings_sp500_2016_2025", max_events=None)
        if _has_usable_atoms(e.event_id)
    ]
    if args.max_events:
        events = events[: args.max_events]

    refreshed = 0
    eligible_before = 0
    eligible_after = 0
    generic_before = 0

    for event in events:
        doc = load_catalog_claims(event.event_id)
        if not doc or not doc.get("accepted"):
            continue
        if apply_catalog_claims_policy(doc):
            eligible_before += 1
        if needs_quality_refresh(doc):
            generic_before += 1

        refined = refine_stored_claims_doc({**doc, "refined_at": _utc_now()})
        if apply_catalog_claims_policy(refined):
            eligible_after += 1

        if not args.dry_run:
            path = causal_claims_path(event.event_id)
            path.write_text(json.dumps(refined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        refreshed += 1

    summary = {
        "refined_events": refreshed,
        "needs_refresh_before": generic_before,
        "quality_eligible_before": eligible_before,
        "quality_eligible_after": eligible_after,
        "dry_run": args.dry_run,
        "computed_at": _utc_now(),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
