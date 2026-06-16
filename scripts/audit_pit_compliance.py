#!/usr/bin/env python3
"""Audit PIT temporal envelope compliance for case studies and catalog atoms."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_causal_engine.benchmark.models import load_corpus
from market_causal_engine.benchmark.validation import CASE_STUDY_ABLATION_IDS
from market_causal_engine.case_study import list_case_studies
from market_causal_engine.evidence import load_atoms
from market_causal_engine.lookahead import LookAheadPolicy
from market_causal_engine.platform.pit_hardening import (
    CaseTimeAxis,
    audit_atoms_pit,
    audit_case_study,
    summarize_pit_compliance,
)


def audit_all_case_studies(*, as_of: int = 120) -> list[dict]:
    reports: list[dict] = []
    for case in list_case_studies():
        case_id = case["case_id"]
        try:
            reports.append(audit_case_study(case_id, as_of_minutes=as_of))
        except FileNotFoundError:
            continue
    return reports


def audit_catalog_sample(*, max_events: int = 20, seed: int = 1, as_of: int = 120) -> list[dict]:
    from market_causal_engine.benchmark.catalog.replay import has_catalog_atoms
    from market_causal_engine.benchmark.catalog.store import load_manifest

    events = load_corpus("earnings_sp500_2016_2025", max_events=max_events, seed=seed)
    reports: list[dict] = []
    policy = LookAheadPolicy()
    for event in events:
        if not has_catalog_atoms(event.event_id):
            continue
        try:
            manifest = load_manifest(event.event_id)
            atoms = load_atoms(manifest.get("atoms_path") or f"data/benchmark/catalog/{event.event_id}/atoms.jsonl")
            pit_manifest = {
                "event_date": event.event_date,
                "filing_date": manifest.get("filing_date") or manifest.get("aligned_filing_date"),
                "aligned_filing_date": manifest.get("aligned_filing_date"),
            }
            axis = CaseTimeAxis.from_manifest(pit_manifest)
            report = audit_atoms_pit(atoms, axis=axis, as_of_minutes=as_of, policy=policy)
            row = report.to_dict()
            row["event_id"] = event.event_id
            reports.append(row)
        except (FileNotFoundError, ValueError, OSError):
            continue
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PIT compliance for evidence fixtures")
    parser.add_argument("--as-of", type=int, default=120, help="Simulation horizon in minutes")
    parser.add_argument("--catalog-sample", type=int, default=0, help="Sample N catalog events (0=skip)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", type=str, default="", help="Write JSON report path")
    args = parser.parse_args()

    case_reports = audit_all_case_studies(as_of=args.as_of)
    catalog_reports: list[dict] = []
    if args.catalog_sample > 0:
        catalog_reports = audit_catalog_sample(max_events=args.catalog_sample, seed=args.seed, as_of=args.as_of)

    summary = {
        "case_studies": summarize_pit_compliance(case_reports),
        "catalog_sample": summarize_pit_compliance(catalog_reports) if catalog_reports else {"n": 0},
        "case_reports": case_reports,
        "catalog_reports": catalog_reports,
        "default_ablation_cases": CASE_STUDY_ABLATION_IDS,
    }

    print(json.dumps(summary["case_studies"], indent=2))
    if catalog_reports:
        print("\nCatalog sample:", json.dumps(summary["catalog_sample"], indent=2))

    failed_cases = [r for r in case_reports if not r.get("passed")]
    if failed_cases:
        print(f"\n{len(failed_cases)} case study(ies) failed PIT audit:")
        for r in failed_cases:
            print(f"  - {r.get('case_id')}: {r.get('error_count')} errors")

    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")

    return 0 if summary["case_studies"].get("all_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
