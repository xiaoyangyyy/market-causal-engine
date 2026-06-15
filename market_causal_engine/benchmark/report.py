"""Benchmark report generation: JSON, Markdown, human-review CSV."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.benchmark.metrics import EventScore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_human_review_csv(path: Path, scores: list[EventScore]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_id",
        "corpus",
        "ticker",
        "event_date",
        "domain",
        "observed_direction",
        "simulated_direction",
        "direction_match",
        "calibration_error_pct",
        "drawdown_risk",
        "dominant_path",
        "synthetic_labels",
        "analyst_rating_1_to_5",
        "analyst_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in scores:
            writer.writerow(
                {
                    "event_id": s.event_id,
                    "corpus": s.corpus,
                    "ticker": "",
                    "event_date": "",
                    "domain": s.domain,
                    "observed_direction": s.observed_direction or "",
                    "simulated_direction": s.simulated_direction or "",
                    "direction_match": s.direction_match,
                    "calibration_error_pct": s.calibration_error_pct,
                    "drawdown_risk": round(s.drawdown_risk, 4),
                    "dominant_path": " → ".join(s.dominant_path[:6]),
                    "synthetic_labels": s.synthetic_labels,
                    "analyst_rating_1_to_5": "",
                    "analyst_notes": "",
                }
            )


def write_human_review_csv_enriched(
    path: Path,
    scores: list[EventScore],
    events_by_id: dict[str, Any],
    *,
    priority_sample_path: Path | None = None,
    priority_n: int = 50,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_id",
        "corpus",
        "ticker",
        "event_date",
        "domain",
        "observed_direction",
        "simulated_direction",
        "direction_match",
        "calibration_error_pct",
        "drawdown_risk",
        "dominant_path",
        "synthetic_labels",
        "analyst_rating_1_to_5",
        "analyst_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in scores:
            ev = events_by_id.get(s.event_id)
            writer.writerow(
                {
                    "event_id": s.event_id,
                    "corpus": s.corpus,
                    "ticker": getattr(ev, "ticker", "") if ev else "",
                    "event_date": getattr(ev, "event_date", "") if ev else "",
                    "domain": s.domain,
                    "observed_direction": s.observed_direction or "",
                    "simulated_direction": s.simulated_direction or "",
                    "direction_match": s.direction_match,
                    "calibration_error_pct": s.calibration_error_pct,
                    "drawdown_risk": round(s.drawdown_risk, 4),
                    "dominant_path": " → ".join(s.dominant_path[:6]),
                    "synthetic_labels": s.synthetic_labels,
                    "analyst_rating_1_to_5": "",
                    "analyst_notes": "",
                }
            )

    if priority_sample_path is not None and scores:
        import random

        rng = random.Random(42)
        pool = [s for s in scores if not s.is_placebo]
        real = [s for s in pool if not s.synthetic_labels]
        rest = [s for s in pool if s.synthetic_labels]
        rng.shuffle(real)
        rng.shuffle(rest)
        picked = (real + rest)[:priority_n]
        with priority_sample_path.open("w", encoding="utf-8", newline="") as pf:
            pw = csv.DictWriter(pf, fieldnames=fields)
            pw.writeheader()
            for s in picked:
                ev = events_by_id.get(s.event_id)
                pw.writerow(
                    {
                        "event_id": s.event_id,
                        "corpus": s.corpus,
                        "ticker": getattr(ev, "ticker", "") if ev else "",
                        "event_date": getattr(ev, "event_date", "") if ev else "",
                        "domain": s.domain,
                        "observed_direction": s.observed_direction or "",
                        "simulated_direction": s.simulated_direction or "",
                        "direction_match": s.direction_match,
                        "calibration_error_pct": s.calibration_error_pct,
                        "drawdown_risk": round(s.drawdown_risk, 4),
                        "dominant_path": " → ".join(s.dominant_path[:6]),
                        "synthetic_labels": s.synthetic_labels,
                        "analyst_rating_1_to_5": "",
                        "analyst_notes": "",
                    }
                )


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    run_id = report.get("run_id", "benchmark")
    summary = report.get("summary", {})
    oot = report.get("out_of_time", {})
    ablation = report.get("ablation", {})
    sensitivity = report.get("sensitivity", {})
    lines = [
        f"# Benchmark Report — `{run_id}`",
        "",
        f"Generated: {_utc_now_iso()}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Events replayed | {summary.get('count', 0)} |",
        f"| Direction accuracy (overall) | {_fmt(summary.get('direction_accuracy'))} |",
        f"| OOT train accuracy | {_fmt(oot.get('train_direction_accuracy'))} |",
        f"| OOT test accuracy | {_fmt(oot.get('test_direction_accuracy'))} |",
        f"| Mean cal error (real cases) | {_fmt_pct(summary.get('mean_calibration_error_real_cases_pct'))} |",
        f"| Placebo false-positive rate | {_fmt(summary.get('placebo_false_positive_rate'))} |",
        "",
        "## By corpus",
        "",
    ]
    for corpus, stats in (summary.get("by_corpus") or {}).items():
        lines.append(
            f"- **{corpus}**: n={stats.get('n')} dir_acc={_fmt(stats.get('direction_accuracy'))} "
            f"placebo_fp={_fmt(stats.get('placebo_fp_rate'))}"
        )

    if ablation:
        lines.extend(["", "## Ablation (case studies)", ""])
        by_ch = ablation.get("by_channel") or {}
        for channel, stats in by_ch.items():
            lines.append(
                f"- `{channel}`: flip_rate={_fmt(stats.get('flip_rate'))} "
                f"path_changes={stats.get('path_changes', 0)}"
            )

    if sensitivity:
        lines.extend(
            [
                "",
                "## Sensitivity (±10% priors)",
                "",
                f"- Mean direction flips: {_fmt(sensitivity.get('mean_direction_flips'))}",
                f"- Max direction flips: {sensitivity.get('max_direction_flips', '—')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Catalog earnings use **synthetic proxy labels** for scale testing; full case studies use real observed outcomes.",
            "- Target: placebo FP rate < 5%; document actual above.",
            "- This report is for model validation / governance, not investment advice.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(val: Any) -> str:
    if val is None:
        return "None"
    if isinstance(val, float):
        return f"{val:.3f}"
    return str(val)


def _fmt_pct(val: Any) -> str:
    if val is None:
        return "None"
    return f"{val:.1f}%"
