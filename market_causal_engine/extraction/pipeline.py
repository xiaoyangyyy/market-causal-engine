"""Orchestrate SEC/news source ingestion into case study atom feeds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.evidence import MarketAtom, load_atoms, save_atoms
from market_causal_engine.extraction.news_parser import parse_news_jsonl
from market_causal_engine.extraction.sec_parser import parse_sec_text
from market_causal_engine.lookahead import LookAheadPolicy, validate_feed


def _case_root(case_id: str) -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies" / case_id


def load_sources_manifest(case_id: str) -> dict[str, Any]:
    path = _case_root(case_id) / "sources" / "sources.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing sources manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe_atoms(atoms: list[MarketAtom]) -> list[MarketAtom]:
    seen_text: set[str] = set()
    seen_events: set[tuple[int | None, str]] = set()
    out: list[MarketAtom] = []
    for atom in sorted(atoms, key=lambda a: (a.published_at or a.time, a.atom_id)):
        text_key = atom.text.lower()[:100]
        if text_key in seen_text:
            continue
        rule_id = str(atom.metadata.get("extracted_by", ""))
        event_key = (atom.published_at or atom.time, rule_id)
        if rule_id and event_key in seen_events:
            continue
        seen_text.add(text_key)
        if rule_id:
            seen_events.add(event_key)
        out.append(atom)
    return out


def _edgar_summary_path(root: Path, manifest: dict[str, Any]) -> Path | None:
    edgar_cfg = manifest.get("edgar")
    if not edgar_cfg:
        return None
    name = edgar_cfg.get("summary_output", "sec_8k_edgar_summary.txt")
    path = root / "sources" / name
    return path if path.exists() else None


def _ensure_edgar_summary(root: Path, manifest: dict[str, Any]) -> Path | None:
    """Build summary from raw EDGAR file if summary is missing."""
    summary_path = _edgar_summary_path(root, manifest)
    if summary_path is not None:
        return summary_path

    edgar_cfg = manifest.get("edgar")
    if not edgar_cfg:
        return None

    raw_name = edgar_cfg.get("output", "sec_8k_edgar.txt")
    raw_path = root / "sources" / raw_name
    if not raw_path.exists():
        return None

    from market_causal_engine.extraction.edgar_preprocess import preprocess_edgar_filing

    summary_name = edgar_cfg.get("summary_output", "sec_8k_edgar_summary.txt")
    summary_path = root / "sources" / summary_name
    summary_text = preprocess_edgar_filing(raw_path.read_text(encoding="utf-8"))
    if len(summary_text.strip()) >= 40:
        summary_path.write_text(summary_text, encoding="utf-8")
        return summary_path
    return None


def _load_document_text(root: Path, doc: dict[str, Any], manifest: dict[str, Any]) -> tuple[str, str]:
    """
    Load document text. For SEC 8-K docs, prefer EDGAR summary when available.
    Returns (text, source_label).
    """
    doc_path = root / "sources" / doc["path"]
    source_type = doc.get("source_type", "news")
    prefer_summary = doc.get("prefer_edgar_summary", manifest.get("prefer_edgar_summary", True))

    if source_type in ("sec_8k", "sec_filing") and prefer_summary:
        summary_path = _ensure_edgar_summary(root, manifest)
        if summary_path is not None:
            summary_text = summary_path.read_text(encoding="utf-8").strip()
            if len(summary_text) >= 40:
                return summary_text, "edgar_summary"

    if not doc_path.exists():
        raise FileNotFoundError(doc_path)
    return doc_path.read_text(encoding="utf-8"), doc["path"]


def extract_from_case(case_id: str) -> tuple[list[MarketAtom], dict[str, Any]]:
    """Extract atoms from all documents listed in sources/sources.json."""
    root = _case_root(case_id)
    manifest = load_sources_manifest(case_id)
    prefix = manifest.get("atom_id_prefix", case_id.upper().replace("-", "_")[:12])
    documents = manifest.get("documents", [])

    atoms: list[MarketAtom] = []
    idx = 0
    report_docs: list[dict[str, Any]] = []

    for doc in documents:
        doc_path = root / "sources" / doc["path"]
        try:
            if doc_path.suffix == ".jsonl":
                if not doc_path.exists():
                    report_docs.append({"doc": doc["path"], "status": "missing", "atoms": 0})
                    continue
                batch, idx = parse_news_jsonl(doc_path, case_prefix=prefix, start_index=idx)
                report_docs.append({"doc": doc["path"], "status": "ok", "atoms": len(batch)})
            else:
                text, text_source = _load_document_text(root, doc, manifest)
                source_type = doc.get("source_type", "news")
                offset = int(doc.get("published_offset_min", 0))
                batch, idx = parse_sec_text(
                    text,
                    doc_id=doc.get("doc_id", doc["path"]),
                    source_type=source_type,
                    published_offset_min=offset,
                    case_prefix=prefix,
                    start_index=idx,
                )
                status = "ok" if text_source == doc["path"] else f"ok:{text_source}"
                report_docs.append({"doc": doc["path"], "status": status, "atoms": len(batch)})
            atoms.extend(batch)
        except FileNotFoundError:
            report_docs.append({"doc": doc["path"], "status": "missing", "atoms": 0})

    manual = root / "sources" / "manual_atoms.jsonl"
    if manual.exists():
        manual_atoms = load_atoms(manual)
        for i, atom in enumerate(manual_atoms):
            if not atom.atom_id.startswith(prefix):
                atom = MarketAtom(
                    atom_id=f"{prefix}_M{i:02d}",
                    text=atom.text,
                    source=atom.source,
                    time=atom.time,
                    tags=atom.tags,
                    metadata=atom.metadata,
                    published_at=atom.published_at,
                )
            atoms.append(atom)
        report_docs.append({"doc": "manual_atoms.jsonl", "status": "ok", "atoms": len(manual_atoms)})

    atoms = _dedupe_atoms(atoms)
    extraction_report = {
        "case_id": case_id,
        "documents": report_docs,
        "atom_count": len(atoms),
        "atom_id_prefix": prefix,
    }
    return atoms, extraction_report


def build_atoms_for_case(
    case_id: str,
    *,
    as_of: int | None = None,
    write: bool = True,
    validate_lookahead: bool = True,
    fetch_edgar: bool = False,
) -> dict[str, Any]:
    """Extract, validate, and optionally write atoms.jsonl for a case study."""
    if fetch_edgar:
        from market_causal_engine.extraction.edgar_fetch import fetch_edgar_for_case

        try:
            fetch_edgar_for_case(case_id)
        except Exception as exc:
            return {
                "case_id": case_id,
                "error": f"edgar_fetch_failed: {exc}",
            }

    root = _case_root(case_id)
    case_manifest_path = root / "manifest.json"
    if not case_manifest_path.exists():
        raise FileNotFoundError(f"Case manifest not found: {case_manifest_path}")

    case_manifest = json.loads(case_manifest_path.read_text(encoding="utf-8"))
    horizon = as_of or int(case_manifest.get("default_until", 120))
    policy = LookAheadPolicy.from_dict(case_manifest.get("lookahead_policy"))

    atoms, extraction_report = extract_from_case(case_id)
    from market_causal_engine.platform.pit_hardening import CaseTimeAxis, enrich_atoms_temporal

    axis = CaseTimeAxis.from_manifest(case_manifest)
    atoms = enrich_atoms_temporal(atoms, axis)
    lookahead = validate_feed(atoms, as_of=horizon, policy=policy) if validate_lookahead else None

    out_path = root / case_manifest.get("atoms_path", "atoms.jsonl")
    if write:
        save_atoms(atoms, out_path)
        report_path = root / "extraction_report.json"
        full_report = {
            **extraction_report,
            "atoms_path": str(out_path),
            "lookahead": lookahead.to_dict() if lookahead else None,
        }
        report_path.write_text(json.dumps(full_report, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "case_id": case_id,
        "atom_count": len(atoms),
        "atoms_path": str(out_path),
        "extraction": extraction_report,
        "lookahead_passed": lookahead.passed if lookahead else None,
        "lookahead_rejected": len(lookahead.rejected_atoms) if lookahead else 0,
    }


def list_extractable_cases() -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies"
    cases: list[str] = []
    for case_dir in sorted(root.iterdir()):
        if (case_dir / "sources" / "sources.json").exists():
            cases.append(case_dir.name)
    return cases
