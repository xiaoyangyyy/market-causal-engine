"""Orchestrate causal claim extraction: propose -> validate -> score."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.case_study import load_case_manifest
from market_causal_engine.evidence import MarketAtom, load_atoms
from market_causal_engine.extraction.atom_scorer import rank_claims, score_claim
from market_causal_engine.extraction.llm_extractor import propose_claims
from market_causal_engine.extraction.rule_validator import normalize_claim, validate_claim
from market_causal_engine.lookahead import LookAheadPolicy


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _case_root(case_id: str) -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "market" / "case_studies" / case_id


def extract_claims_from_atom(
    atom: MarketAtom,
    *,
    domain: str,
    as_of: int,
    policy: LookAheadPolicy | None = None,
    use_llm: bool = False,
    claim_index: int = 0,
    case_prefix: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    proposals = propose_claims(atom, domain, use_llm=use_llm)
    for proposal in proposals:
        claim = normalize_claim(proposal, atom)
        validation = validate_claim(claim, atom, domain=domain, as_of=as_of, policy=policy)
        record = {
            **claim,
            "atom_id": atom.atom_id,
            "validation": validation.to_dict(),
            "proposer": proposal.get("proposer", "heuristic"),
        }
        if validation.passed:
            scores = score_claim(claim, atom)
            record.update(scores)
            prefix = case_prefix or atom.atom_id.split("_")[0]
            record["claim_id"] = f"{prefix}_C{claim_index:03d}"
            accepted.append(record)
            claim_index += 1
        else:
            rejected.append(record)

    return accepted, rejected


def extract_claims_for_atoms(
    atoms: list[MarketAtom],
    *,
    domain: str,
    as_of: int,
    policy: LookAheadPolicy | None = None,
    use_llm: bool = False,
    case_prefix: str = "",
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    idx = 0

    for atom in sorted(atoms, key=lambda a: (a.effective_time(), a.atom_id)):
        batch_ok, batch_rej = extract_claims_from_atom(
            atom,
            domain=domain,
            as_of=as_of,
            policy=policy,
            use_llm=use_llm,
            claim_index=idx,
            case_prefix=case_prefix,
        )
        accepted.extend(batch_ok)
        rejected.extend(batch_rej)
        idx += len(batch_ok)

    accepted = rank_claims(accepted)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "claim_count": len(accepted),
        "rejected_count": len(rejected),
    }


def extract_claims_for_case(
    case_id: str,
    *,
    as_of: int | None = None,
    use_llm: bool = False,
    write: bool = True,
) -> dict[str, Any]:
    manifest = load_case_manifest(case_id)
    root = _case_root(case_id)
    atoms_path = root / manifest.get("atoms_path", "atoms.jsonl")
    if not atoms_path.exists():
        raise FileNotFoundError(f"Missing atoms for case {case_id}: {atoms_path}")

    atoms = load_atoms(atoms_path)
    domain = str(manifest.get("domain", manifest.get("event_type", "earnings")))
    if domain not in ("earnings", "short_report", "macro"):
        domain = {
            "short_squeeze": "short_report",
            "short_report": "short_report",
            "fomc": "macro",
            "cpi": "macro",
        }.get(domain, "earnings")

    horizon = as_of if as_of is not None else int(manifest.get("default_until", 180))
    policy = LookAheadPolicy.from_dict(manifest.get("lookahead_policy"))
    prefix = case_id.upper().replace("-", "_")[:12]

    result = extract_claims_for_atoms(
        atoms,
        domain=domain,
        as_of=horizon,
        policy=policy,
        use_llm=use_llm,
        case_prefix=prefix,
    )

    out = {
        "case_id": case_id,
        "domain": domain,
        "as_of": horizon,
        "use_llm": use_llm,
        "computed_at": _utc_now(),
        **result,
    }

    if write:
        out_path = root / "causal_claims.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out["artifact"] = str(out_path)

        manifest_path = root / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["causal_claims"] = {
            "claim_count": out["claim_count"],
            "rejected_count": out["rejected_count"],
            "top_claim": out["accepted"][0] if out["accepted"] else None,
            "artifact": "causal_claims.json",
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return out


def run_all_case_claims(*, use_llm: bool = False) -> dict[str, Any]:
    from market_causal_engine.case_study import list_case_studies

    summaries: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for case in list_case_studies():
        case_id = case["case_id"]
        try:
            summaries[case_id] = extract_claims_for_case(case_id, use_llm=use_llm)
        except Exception as exc:  # noqa: BLE001
            errors.append({"case_id": case_id, "error": str(exc)})

    aggregate = {
        "cases": len(summaries) + len(errors),
        "ok": len(summaries),
        "errors": errors,
        "total_claims": sum(s.get("claim_count", 0) for s in summaries.values()),
        "results": summaries,
        "computed_at": _utc_now(),
    }

    out_dir = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "causal_claims"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_studies_summary.json").write_text(
        json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return aggregate
