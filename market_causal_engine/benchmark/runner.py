"""Benchmark runner orchestrating replay, validation, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.metrics import (
    aggregate_scores,
    confidence_stability,
    oot_accuracy,
    score_event,
    split_by_date,
)
from market_causal_engine.benchmark.models import BenchmarkEvent, load_all_corpora, load_corpus
from market_causal_engine.benchmark.replay import replay_event
from market_causal_engine.benchmark.report import (
    write_human_review_csv_enriched,
    write_json_report,
    write_markdown_report,
)
from market_causal_engine.benchmark.validation import (
    run_ablation_suite,
    run_sensitivity_on_scenario,
    summarize_ablation,
    summarize_sensitivity,
)
from market_causal_engine.platform.provenance import new_run_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class BenchmarkConfig:
    corpora: list[str] | None = None
    max_events_per_corpus: int | None = 200
    until: int = 120
    oot_cutoff_date: str = "2022-01-01"
    placebo_drawdown_threshold: float = 0.35
    placebo_pressure_threshold: float = 0.20
    run_ablation: bool = True
    run_sensitivity: bool = False
    sensitivity_sample: int = 3
    output_dir: Path = field(default_factory=lambda: Path("results/benchmark"))
    seed: int = 42
    include_placebo: bool = True


class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig | None = None) -> None:
        self.config = config or BenchmarkConfig()

    def load_events(self) -> list[BenchmarkEvent]:
        if self.config.corpora:
            corpora = list(self.config.corpora)
        else:
            corpora = [
                "earnings_sp500_2016_2025",
                "short_reports_public",
                "macro_releases",
                "company_shocks",
            ]
        if self.config.include_placebo and "placebo_quiet_days" not in corpora:
            corpora.append("placebo_quiet_days")
        return load_all_corpora(
            corpora,
            max_events_per_corpus=self.config.max_events_per_corpus,
            seed=self.config.seed,
        )

    def run(self, *, run_id: str | None = None) -> dict[str, Any]:
        rid = run_id or new_run_id("benchmark")
        events = self.load_events()
        scores = []
        errors: list[dict[str, str]] = []

        for event in events:
            try:
                result = replay_event(event, until=self.config.until)
                scores.append(
                    score_event(
                        event,
                        result,
                        placebo_drawdown_threshold=self.config.placebo_drawdown_threshold,
                        placebo_pressure_threshold=self.config.placebo_pressure_threshold,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"event_id": event.event_id, "error": str(exc)})

        summary = aggregate_scores(scores)
        train, test = split_by_date(scores, events, cutoff_date=self.config.oot_cutoff_date)
        oot = oot_accuracy(train, test)
        confidence = confidence_stability(scores)

        ablation_summary: dict[str, Any] = {}
        if self.config.run_ablation:
            ablation_results = run_ablation_suite(until=self.config.until)
            ablation_summary = summarize_ablation(ablation_results)

        sensitivity_summary: dict[str, Any] = {}
        if self.config.run_sensitivity:
            sens_events = [e for e in events if e.replay_mode == "scenario"][: self.config.sensitivity_sample]
            sens_results = [
                run_sensitivity_on_scenario(ev, until=self.config.until) for ev in sens_events
            ]
            sensitivity_summary = summarize_sensitivity(sens_results)

        report = {
            "run_id": rid,
            "generated_at": _utc_now_iso(),
            "config": {
                "corpora": self.config.corpora,
                "max_events_per_corpus": self.config.max_events_per_corpus,
                "until": self.config.until,
                "oot_cutoff_date": self.config.oot_cutoff_date,
                "seed": self.config.seed,
            },
            "summary": summary,
            "out_of_time": oot,
            "confidence": confidence,
            "ablation": ablation_summary,
            "sensitivity": sensitivity_summary,
            "errors": errors,
            "scores": [s.to_dict() for s in scores],
        }

        out_dir = self.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json_report(out_dir / f"{rid}.json", report)
        write_markdown_report(out_dir / f"{rid}_report.md", report)
        events_by_id = {e.event_id: e for e in events}
        write_human_review_csv_enriched(
            out_dir / f"{rid}_human_review.csv",
            scores,
            events_by_id,
            priority_sample_path=out_dir / f"{rid}_human_review_priority50.csv",
        )

        report["artifacts"] = {
            "json": str(out_dir / f"{rid}.json"),
            "markdown": str(out_dir / f"{rid}_report.md"),
            "human_review_csv": str(out_dir / f"{rid}_human_review.csv"),
            "human_review_priority50_csv": str(out_dir / f"{rid}_human_review_priority50.csv"),
        }
        return report
