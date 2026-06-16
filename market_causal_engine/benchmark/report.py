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


def write_failed_cases_report(path: Path, failed: list[dict[str, Any]]) -> None:
    lines = [
        "# Benchmark Failed Cases (real-label direction mismatches)",
        "",
        "Public appendix — documents where the model predicted the wrong direction.",
        "",
        "| event_id | corpus | observed | simulated | path | router | drawdown |",
        "|----------|--------|----------|-----------|------|--------|----------|",
    ]
    for row in failed:
        lines.append(
            f"| {row.get('event_id', '')} | {row.get('corpus', '')} | "
            f"{row.get('observed_direction', '')} | {row.get('simulated_direction', '')} | "
            f"{row.get('replay_mode', '')} | {row.get('router_preferred', '')} | "
            f"{row.get('drawdown_risk', '')} |"
        )
    if not failed:
        lines.append("| — | — | — | — | — | — | — |")
    lines.extend(["", f"Total documented: {len(failed)}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    run_id = report.get("run_id", "benchmark")
    headline = report.get("headline", {})
    appendix = report.get("appendix", {})
    summary = report.get("summary", {})
    oot = report.get("out_of_time", {})
    catalog = report.get("catalog_only", {})
    baselines = headline.get("naive_baselines_real_label") or {}
    ablation = report.get("ablation", {})
    sensitivity = report.get("sensitivity", {})
    pit = report.get("pit_compliance", {})

    lines = [
        f"# Benchmark Report — `{run_id}`",
        "",
        f"Generated: {_utc_now_iso()}",
        "",
        "## Headline metrics (real-label only)",
        "",
        "_Use these for README / external reporting. Do not cite mixed overall accuracy._",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Real-label events | {headline.get('real_label_n', 0)} |",
        f"| Real-label direction accuracy | {_fmt(headline.get('real_label_direction_accuracy'))} |",
        f"| Placebo false-positive rate | {_fmt(headline.get('placebo_false_positive_rate'))} |",
        f"| **Catalog-only EDGAR path** | {_fmt(catalog.get('catalog_only_direction_accuracy'))} (n={catalog.get('catalog_only_n', '—')}) |",
        f"| OOT test (real-label, post-{report.get('config', {}).get('oot_cutoff_date', '2022')}) | {_fmt(oot.get('test_direction_accuracy'))} |",
        "",
        "### By corpus (real-label subset)",
        "",
    ]
    for corpus, stats in (headline.get("by_corpus_real_label") or {}).items():
        lines.append(
            f"- **{corpus}**: n={stats.get('n')} dir_acc={_fmt(stats.get('direction_accuracy'))}"
        )

    if baselines:
        lines.extend(
            [
                "",
                "### Naive baselines (real-label)",
                "",
                f"- Always-neutral accuracy: {_fmt(baselines.get('always_neutral_accuracy'))}",
                f"- Always-majority ({baselines.get('majority_class', '?')}): "
                f"{_fmt(baselines.get('always_majority_class_accuracy'))}",
                f"- Class distribution: `{baselines.get('class_distribution', {})}`",
            ]
        )

    lines.extend(
        [
            "",
            "### Router path split (real-label earnings)",
            "",
            f"- Catalog path: n={headline.get('real_label_catalog_path_n', 0)} "
            f"acc={_fmt(headline.get('real_label_catalog_path_direction_accuracy'))}",
            f"- Scenario router path: n={headline.get('real_label_scenario_router_path_n', 0)} "
            f"acc={_fmt(headline.get('real_label_scenario_router_path_direction_accuracy'))}",
            "",
            "## Appendix — mixed / legacy (not headline)",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Mixed overall direction accuracy | {_fmt(appendix.get('mixed_overall_direction_accuracy'))} |",
            f"| Proxy-label events in run | {headline.get('proxy_label_n', 0)} |",
            f"| Legacy summary count | {summary.get('count', 0)} |",
            "",
            f"_{appendix.get('note', '')}_",
            "",
        ]
    )

    if ablation:
        lines.extend(["## Ablation (case studies)", ""])
        by_ch = ablation.get("by_channel") or {}
        for channel, stats in by_ch.items():
            lines.append(
                f"- `{channel}`: flip_rate={_fmt(stats.get('flip_rate'))} "
                f"path_changes={stats.get('path_changes', 0)}"
            )
        car_by_ch = ablation.get("car_by_channel") or {}
        if car_by_ch:
            lines.extend(["", "### Marginal CAR contribution by channel", ""])
            for channel, stats in car_by_ch.items():
                lines.append(
                    f"- `{channel}`: mean_share_of_observed_car="
                    f"{_fmt(stats.get('mean_share_of_observed_car'))} "
                    f"mean_marginal_return_pct={_fmt(stats.get('mean_marginal_return_pct'))} "
                    f"(n={stats.get('n', 0)})"
                )
        car_cases = ablation.get("car_by_case") or {}
        if car_cases:
            lines.extend(["", "### Per-case dominant channel (CAR)", ""])
            for case_id, car in car_cases.items():
                lines.append(
                    f"- `{case_id}`: dominant=`{car.get('dominant_channel')}` "
                    f"share={_fmt(car.get('dominant_share_of_observed_car'))} "
                    f"observed_car_pct={_fmt(car.get('observed_car_pct'))}"
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

    if pit:
        lines.extend(
            [
                "",
                "## PIT compliance (case-study fixtures)",
                "",
                f"- Cases audited: {pit.get('n', 0)} | passed: {pit.get('passed', 0)} | "
                f"all_passed: {pit.get('all_passed')}",
                f"- Mean envelope coverage: {_fmt(pit.get('mean_envelope_coverage'))}",
            ]
        )
        for case_id, row in (pit.get("cases") or {}).items():
            if not row.get("passed"):
                lines.append(
                    f"- FAIL `{case_id}`: errors={row.get('error_count')} "
                    f"coverage={_fmt(row.get('envelope_coverage'))}"
                )

    failed = report.get("failed_cases") or []
    if failed:
        lines.extend(["", "## Failed cases (top 10 real-label mismatches)", ""])
        for row in failed[:10]:
            lines.append(
                f"- `{row.get('event_id')}`: obs={row.get('observed_direction')} "
                f"sim={row.get('simulated_direction')} router={row.get('router_preferred')} "
                f"path={row.get('replay_mode')}"
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- **Catalog-only** = quality-filtered EDGAR atoms + LLM claims, no scenario router.",
            "- **Real-label** = Yahoo daily or case-study observed outcomes; proxy labels excluded from headline.",
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
