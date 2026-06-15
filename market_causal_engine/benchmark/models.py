"""Benchmark event models and corpus loaders."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "benchmark"

CORPORA: dict[str, str] = {
    "earnings_sp500_2016_2025": "S&P-style earnings catalog (scenario replay + proxy labels)",
    "short_reports_public": "Public short report events (case + scenario)",
    "macro_releases": "CPI/FOMC macro releases",
    "company_shocks": "Guidance cut, fraud, FDA, CEO exit",
    "placebo_quiet_days": "Quiet days — false-positive control",
}


@dataclass
class BenchmarkEvent:
    event_id: str
    corpus: str
    ticker: str
    event_date: str
    event_type: str
    domain: str
    replay_mode: str
    observed_outcomes: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    scenario_id: str | None = None
    case_id: str | None = None
    fiscal_period: str | None = None
    outcome_causal: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkEvent:
        return cls(
            event_id=str(data["event_id"]),
            corpus=str(data.get("corpus", "")),
            ticker=str(data.get("ticker", "")),
            event_date=str(data.get("event_date", "")),
            event_type=str(data.get("event_type", "")),
            domain=str(data.get("domain", "")),
            replay_mode=str(data.get("replay_mode", "scenario")),
            observed_outcomes=dict(data.get("observed_outcomes", {})),
            labels=dict(data.get("labels", {})),
            metadata=dict(data.get("metadata", {})),
            scenario_id=data.get("scenario_id"),
            case_id=data.get("case_id"),
            fiscal_period=data.get("fiscal_period"),
            outcome_causal=dict(data["outcome_causal"]) if data.get("outcome_causal") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "event_id": self.event_id,
            "corpus": self.corpus,
            "ticker": self.ticker,
            "event_date": self.event_date,
            "event_type": self.event_type,
            "domain": self.domain,
            "replay_mode": self.replay_mode,
            "observed_outcomes": self.observed_outcomes,
            "labels": self.labels,
            "metadata": self.metadata,
        }
        if self.scenario_id:
            out["scenario_id"] = self.scenario_id
        if self.case_id:
            out["case_id"] = self.case_id
        if self.fiscal_period:
            out["fiscal_period"] = self.fiscal_period
        if self.outcome_causal:
            out["outcome_causal"] = self.outcome_causal
        return out

    @property
    def is_placebo(self) -> bool:
        return bool(self.labels.get("is_placebo"))

    @property
    def has_full_case(self) -> bool:
        return bool(self.labels.get("has_full_case")) or self.replay_mode == "case_study"

    @property
    def uses_synthetic_labels(self) -> bool:
        return bool(self.metadata.get("synthetic_labels"))


def benchmark_dir() -> Path:
    return BENCHMARK_DIR


def list_corpora() -> dict[str, str]:
    out = dict(CORPORA)
    for name in CORPORA:
        path = BENCHMARK_DIR / f"{name}.jsonl"
        if path.exists():
            count = sum(1 for line in path.open(encoding="utf-8") if line.strip())
            out[name] = f"{CORPORA[name]} [{count} events]"
    return out


def load_corpus(
    name: str,
    *,
    max_events: int | None = None,
    seed: int = 42,
    major_only: bool = False,
) -> list[BenchmarkEvent]:
    path = BENCHMARK_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark corpus not found: {path}")

    events: list[BenchmarkEvent] = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        ev = BenchmarkEvent.from_dict(json.loads(line))
        if major_only and not ev.labels.get("is_major_event", True):
            continue
        events.append(ev)

    if max_events is not None and len(events) > max_events:
        import random

        rng = random.Random(seed)
        if name.startswith("earnings"):
            # Stratified sample by year for earnings scale tests
            by_year: dict[str, list[BenchmarkEvent]] = {}
            for ev in events:
                year = ev.event_date[:4] if ev.event_date else "unknown"
                by_year.setdefault(year, []).append(ev)
            sampled: list[BenchmarkEvent] = []
            per_year = max(1, max_events // max(len(by_year), 1))
            for year in sorted(by_year):
                bucket = by_year[year]
                rng.shuffle(bucket)
                sampled.extend(bucket[:per_year])
            rng.shuffle(sampled)
            events = sampled[:max_events]
        else:
            rng.shuffle(events)
            events = events[:max_events]

    return events


def load_all_corpora(
    corpora: list[str] | None = None,
    *,
    max_events_per_corpus: int | None = None,
    seed: int = 42,
) -> list[BenchmarkEvent]:
    names = corpora or list(CORPORA.keys())
    out: list[BenchmarkEvent] = []
    for name in names:
        if name not in CORPORA:
            continue
        out.extend(load_corpus(name, max_events=max_events_per_corpus, seed=seed))
    return out


def iter_corpus(name: str) -> Iterator[BenchmarkEvent]:
    path = BENCHMARK_DIR / f"{name}.jsonl"
    for line in path.open(encoding="utf-8"):
        if line.strip():
            yield BenchmarkEvent.from_dict(json.loads(line))
