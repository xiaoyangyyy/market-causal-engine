"""Feed-driven simulation: atoms → clusters → compiled events → kernel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcup_causal_engine.compiler import Compiler, CompiledEvent, load_default_rules
from worldcup_causal_engine.evidence import Atom, EvidenceLedger, load_atoms_from_jsonl
from worldcup_causal_engine.kernel import Kernel


DIRECT_CLAIM_MAP: dict[str, tuple[str, int]] = {
    "blame_referee": ("media_blame_frame", 2),
    "blame_player": ("media_blame_frame", 2),
    "rumor_clip_shared": ("viral_clip_published", 2),
    "fan_conflict_report": ("opposing_fans_contact", 1),
    "transit_complaint": ("transit_delay", 2),
}


class FeedRunner:
    """Process a JSONL atom feed interleaved with kernel execution."""

    def __init__(
        self,
        kernel: Kernel,
        ledger: EvidenceLedger | None = None,
        compiler: Compiler | None = None,
        match_id: str = "M12",
        skip_evidence_ledger: bool = False,
    ):
        self.kernel = kernel
        self.ledger = ledger or EvidenceLedger(match_id=match_id)
        self.compiler = compiler or Compiler(load_default_rules())
        self.skip_evidence_ledger = skip_evidence_ledger
        self._compiled_events: list[CompiledEvent] = []

    def ingest_atom(self, atom: Atom) -> list[CompiledEvent]:
        self.ledger.ingest(atom)
        if self.skip_evidence_ledger:
            return self._direct_emit_atom(atom)
        return self._compile_and_emit()

    def _direct_emit_atom(self, atom: Atom) -> list[CompiledEvent]:
        mapping = DIRECT_CLAIM_MAP.get(atom.claim_type)
        if not mapping:
            return []
        kind, priority = mapping
        compiled = CompiledEvent(
            kind=kind,
            time=atom.time,
            priority=priority,
            payload={
                "severity": min(1.0, atom.confidence),
                "target": atom.target,
                "intensity": atom.confidence,
                "confidence": atom.confidence,
                "dominant_claim": atom.claim_type,
            },
            cause=[f"atom_direct:{atom.atom_id}"],
            cluster_id="",
        )
        self._emit_compiled(compiled)
        self._compiled_events.append(compiled)
        return [compiled]

    def _compile_and_emit(self) -> list[CompiledEvent]:
        new_events = self.compiler.try_compile(self.ledger)
        for compiled in new_events:
            self._emit_compiled(compiled)
            self._compiled_events.append(compiled)
        return new_events

    def _emit_compiled(self, compiled: CompiledEvent) -> None:
        self.kernel.emit(
            kind=compiled.kind,
            payload=compiled.payload,
            at_time=compiled.time,
            priority=compiled.priority,
            cause=compiled.cause,
        )

    def run_feed(
        self,
        atoms: list[Atom],
        until: int = 120,
    ) -> list[CompiledEvent]:
        if not atoms:
            self.kernel.run(until=until)
            return []

        times = sorted({a.time for a in atoms})
        time_index = 0

        for atom in atoms:
            while time_index < len(times) and times[time_index] < atom.time:
                self.kernel.run(until=times[time_index])
                time_index += 1
            self.ingest_atom(atom)

        self.kernel.run(until=until)
        return self._compiled_events

    def run_feed_file(self, path: str | Path, until: int = 120) -> list[CompiledEvent]:
        atoms = load_atoms_from_jsonl(path)
        return self.run_feed(atoms, until=until)


def inject_compiled_events(kernel: Kernel, events: list[CompiledEvent]) -> None:
    for compiled in events:
        kernel.emit(
            kind=compiled.kind,
            payload=compiled.payload,
            at_time=compiled.time,
            priority=compiled.priority,
            cause=compiled.cause,
        )
