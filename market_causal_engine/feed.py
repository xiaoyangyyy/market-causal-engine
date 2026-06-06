"""Feed runner: atoms -> compiler -> kernel events with look-ahead guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.compiler import MarketCompiler, load_compiler_rules
from market_causal_engine.evidence import MarketAtom, load_atoms
from market_causal_engine.kernel import Kernel
from market_causal_engine.lookahead import (
    LookAheadPolicy,
    LookAheadReport,
    filter_admissible_atoms,
    validate_atom,
)

# Feed-ingested events: emit at most once per replay (kernel cascades handle the rest).
_SINGLE_SHOT_EVENT_KINDS = frozenset(
    {"ad_revenue_miss", "digital_ad_slowdown", "macro_ad_budget_cut"}
)

# Collapse duplicate compiled events within a sliding window (minutes).
_WINDOWED_EVENT_MINUTES: dict[str, int] = {
    "guidance_cut": 45,
    "analyst_downgrade": 45,
    "institutional_rebalance": 30,
    "option_gamma_pressure": 30,
    "price_impact_amplified": 15,
}


class FeedRunner:
    def __init__(
        self,
        kernel: Kernel,
        *,
        ticker: str = "ACME",
        compiler_rules_path: str | Path | None = None,
        skip_evidence_ledger: bool = False,
        lookahead_policy: LookAheadPolicy | None = None,
        as_of: int | None = None,
    ):
        self.kernel = kernel
        self.ticker = ticker
        self.skip_evidence_ledger = skip_evidence_ledger
        self.lookahead_policy = lookahead_policy or LookAheadPolicy()
        self.as_of = as_of
        rules_path = compiler_rules_path or (
            Path(__file__).resolve().parent.parent
            / "data"
            / "market"
            / "compiler_rules"
            / "v0.1.json"
        )
        self.compiler = MarketCompiler(load_compiler_rules(rules_path))
        self._compiled_events: list[Any] = []
        self._rejected_lookahead: list[dict[str, Any]] = []
        self._emitted_event_keys: set[tuple[str, int]] = set()
        self.lookahead_report: LookAheadReport | None = None
        self.ledger = None
        if not skip_evidence_ledger and kernel.ledger is not None:
            self.ledger = kernel.ledger

    def _coalesce_key(self, event_kind: str, event_time: int) -> tuple[str, int]:
        if event_kind in _SINGLE_SHOT_EVENT_KINDS:
            return (f"single:{event_kind}", 0)
        window = _WINDOWED_EVENT_MINUTES.get(event_kind)
        if window:
            return (event_kind, event_time // window)
        return (event_kind, event_time)

    def ingest_atom(self, atom: MarketAtom, *, skip_validation: bool = False) -> bool:
        if not skip_validation and self.as_of is not None:
            vr = validate_atom(atom, as_of=self.as_of, policy=self.lookahead_policy)
            if not vr.accepted:
                self._rejected_lookahead.append(vr.to_dict())
                return False

        compiled = self.compiler.compile_atom(atom)
        if compiled is None:
            return False

        event_key = self._coalesce_key(compiled.event_kind, compiled.time)
        if event_key in self._emitted_event_keys:
            return True

        self._emitted_event_keys.add(event_key)
        self._compiled_events.append(compiled)
        self.kernel.emit(
            kind=compiled.event_kind,
            payload={"severity": compiled.severity, **compiled.payload},
            at_time=compiled.time,
            priority=2,
            cause=[f"atom:{compiled.source_cluster_id}"],
        )
        return True

    def run_atoms(self, atoms: list[MarketAtom], until: int = 30) -> None:
        ordered = sorted(atoms, key=lambda a: (a.effective_time(), a.atom_id))
        for atom in ordered:
            if atom.effective_time() <= until:
                self.ingest_atom(atom, skip_validation=True)
        self.kernel.run(until=until)

    def run_feed_file(
        self,
        path: str | Path,
        until: int = 30,
        *,
        enforce_lookahead: bool = True,
    ) -> None:
        atoms = load_atoms(path)
        horizon = self.as_of if self.as_of is not None else until

        if enforce_lookahead and self.lookahead_policy.strict:
            atoms, self.lookahead_report = filter_admissible_atoms(
                atoms, as_of=horizon, policy=self.lookahead_policy
            )
        else:
            atoms = [a for a in atoms if a.effective_time() <= until]

        self.run_atoms(atoms, until=until)

    def run_feed_jsonl(self, lines: list[str], until: int = 30) -> None:
        atoms: list[MarketAtom] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            atoms.append(
                MarketAtom(
                    atom_id=raw["atom_id"],
                    text=raw["text"],
                    source=raw.get("source", "unknown"),
                    time=int(raw["time"]),
                    tags=list(raw.get("tags", [])),
                    metadata=dict(raw.get("metadata", {})),
                    published_at=int(raw["published_at"]) if "published_at" in raw else None,
                )
            )
        self.run_atoms(atoms, until=until)
