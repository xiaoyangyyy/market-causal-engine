"""Fetch EDGAR 8-K filings and extract atoms for catalog events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.models import BenchmarkEvent
from market_causal_engine.benchmark.labels import compute_earnings_return, fetch_ticker_daily_bars
from market_causal_engine.evidence import save_atoms
from market_causal_engine.extraction.edgar_fetch import EdgarFiling
from market_causal_engine.extraction.edgar_preprocess import preprocess_edgar_filing, prioritize_exhibit_text
from market_causal_engine.extraction.sec_parser import parse_sec_document

from market_causal_engine.benchmark.catalog.edgar_lookup import fetch_earnings_8k_for_event
from market_causal_engine.benchmark.catalog.fiscal import fiscal_period_date_range
from market_causal_engine.benchmark.catalog.store import (
    catalog_event_dir,
    load_manifest,
    manifest_path,
    sec_text_path,
    write_manifest,
)


def _atom_prefix(event: BenchmarkEvent) -> str:
    ticker = event.ticker.upper()[:6]
    period = (event.fiscal_period or event.event_id).replace("_earnings", "").replace("_", "")[:8]
    return f"{ticker}{period}"[:16]


def build_atoms_for_event(
    event: BenchmarkEvent,
    *,
    overwrite: bool = False,
    window_days: int = 7,
    offline_text: str | None = None,
    offline_filing: EdgarFiling | None = None,
) -> dict[str, Any]:
    """
    Download (or inject) 8-K text, parse atoms, persist under data/benchmark/catalog/{event_id}/.
    """
    root = catalog_event_dir(event.event_id)
    atoms_file = root / "atoms.jsonl"

    if atoms_file.exists() and not overwrite:
        return load_manifest(event.event_id)

    root.mkdir(parents=True, exist_ok=True)

    filing_meta: dict[str, Any]
    if offline_text is not None:
        text = offline_text
        filing_meta = {
            "offline": True,
            "filing_date": event.event_date,
            "accession_number": "offline",
        }
    else:
        fetch_meta: dict[str, str | int | None] = {}
        try:
            text, filing, fetch_meta = fetch_earnings_8k_for_event(event, window_days=window_days)
        except FileNotFoundError:
            raise
        filing_meta = {
            "filing_date": filing.filing_date,
            "accession_number": filing.accession_number,
            "document_url": filing.document_url(),
            "form": filing.form,
            **fetch_meta,
        }
        if fiscal := fiscal_period_date_range(event.fiscal_period):
            filing_meta["search_date_from"] = fiscal[0]
            filing_meta["search_date_to"] = fiscal[1]

    if len(text) > 120_000:
        text = text[:120_000] + "\n\n[truncated for catalog pipeline]"

    summary = preprocess_edgar_filing(text)
    exhibit_first = prioritize_exhibit_text(text)
    source_type = "sec_6k" if filing_meta.get("form") == "6-K" else "sec_8k"
    parse_candidates = []
    for candidate in (exhibit_first, summary, text):
        if candidate and candidate not in parse_candidates and len(candidate) >= 80:
            parse_candidates.append(candidate)
    prefix = _atom_prefix(event)
    atoms: list = []
    for candidate in parse_candidates:
        atoms, _ = parse_sec_document(
            candidate,
            doc_id=f"{event.event_id}_8k",
            source_type=source_type,
            published_offset_min=0,
            case_prefix=prefix,
            heuristic_fallback=True,
        )
        if atoms:
            break

    sec_text_path(event.event_id).write_text(text, encoding="utf-8")
    if summary:
        (root / "sec_8k_summary.txt").write_text(summary, encoding="utf-8")
    save_atoms(atoms, atoms_file)

    report: dict[str, Any] = {
        "event_id": event.event_id,
        "ticker": event.ticker,
        "event_date": event.event_date,
        "fiscal_period": event.fiscal_period,
        "atom_count": len(atoms),
        "text_length": len(text),
        "summary_length": len(summary),
        "atoms_path": str(atoms_file),
        "sec_text_path": str(sec_text_path(event.event_id)),
        **filing_meta,
    }
    filing_date = str(filing_meta.get("filing_date", ""))
    if filing_date and not filing_meta.get("offline"):
        try:
            bars = fetch_ticker_daily_bars(event.ticker)
            aligned = compute_earnings_return(bars, filing_date)
            if aligned:
                report["aligned_filing_date"] = filing_date
                report["aligned_observed_outcomes"] = {
                    "direction": aligned["direction"],
                    "after_hours_return_pct": aligned["after_hours_return_pct"],
                    "magnitude_bucket": aligned["magnitude_bucket"],
                }
                report["labels"] = {"is_major_event": abs(aligned["after_hours_return_pct"]) >= 3.0}
        except Exception:  # noqa: BLE001
            pass
    write_manifest(event.event_id, report)
    return report


def build_atoms_batch(
    events: list[BenchmarkEvent],
    *,
    overwrite: bool = False,
    max_events: int | None = None,
    major_only: bool = False,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """Build catalog atoms for many events; collect successes and errors."""
    selected = events
    if major_only:
        selected = [e for e in selected if e.labels.get("is_major_event")]
    if max_events is not None:
        selected = selected[:max_events]

    stats = {"attempted": 0, "built": 0, "skipped": 0, "empty_atoms": 0, "errors": []}
    for event in selected:
        atoms_file = catalog_event_dir(event.event_id) / "atoms.jsonl"
        if skip_existing and atoms_file.exists() and not overwrite:
            stats["skipped"] += 1
            continue

        stats["attempted"] += 1
        try:
            report = build_atoms_for_event(event, overwrite=overwrite)
            if report.get("atom_count", 0) == 0:
                stats["empty_atoms"] += 1
            else:
                stats["built"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append({"event_id": event.event_id, "ticker": event.ticker, "error": str(exc)})

    return stats
