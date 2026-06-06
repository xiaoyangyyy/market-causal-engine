#!/usr/bin/env python3
"""Generate paper figures from experiment JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def plot_risk_heatmap(summary: dict, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        _write_json_fallback(out_dir / "fig4_risk_heatmap.json", summary)
        return

    results = summary.get("results", [])
    scenarios = sorted({r["scenario_id"] for r in results})
    worlds = sorted({r["world_id"] for r in results})
    data = np.zeros((len(scenarios), len(worlds)))
    for i, sc in enumerate(scenarios):
        for j, w in enumerate(worlds):
            row = next((r for r in results if r["scenario_id"] == sc and r["world_id"] == w), None)
            if row:
                data[i, j] = row.get("final_risk", {}).get("verbal_conflict", 0)

    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(range(len(worlds)), worlds)
    ax.set_yticks(range(len(scenarios)), [s[:20] for s in scenarios])
    ax.set_title("Fig.4 Verbal Conflict Risk (scenario × world)")
    plt.colorbar(im, ax=ax, label="verbal_conflict")
    fig.tight_layout()
    fig.savefig(out_dir / "fig4_risk_heatmap.png", dpi=300)
    fig.savefig(out_dir / "fig4_risk_heatmap.pdf")
    plt.close(fig)


def plot_ablation(summary: dict, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        _write_json_fallback(out_dir / "fig5_ablation.json", summary)
        return

    results = [r for r in summary.get("results", []) if r.get("scenario_id", "").startswith("S1")]
    labels = [r.get("label", r.get("ablation_id")) for r in results]
    verbal = [r.get("final_verbal_conflict_risk", 0) for r in results]
    blocked = [r.get("blocked_events_count", 0) for r in results]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(range(len(labels)), verbal, color="steelblue")
    axes[0].set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    axes[0].set_title("Verbal conflict risk")
    axes[0].set_ylim(0, 1)

    axes[1].bar(range(len(labels)), blocked, color="coral")
    axes[1].set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    axes[1].set_title("Blocked events")

    fig.suptitle("Fig.5 Ablation comparison (S1)")
    fig.tight_layout()
    fig.savefig(out_dir / "fig5_ablation.png", dpi=300)
    fig.savefig(out_dir / "fig5_ablation.pdf")
    plt.close(fig)


def plot_diff_trace(out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    w0 = _load_json(ROOT / "results" / "S1_W0.json")
    w1 = _load_json(ROOT / "results" / "S1_W1.json")
    if not w0 or not w1:
        w0 = _load_json(ROOT / "results" / "experiment_1" / "S1_controversial_call_high_density_W0.json")
        w1 = _load_json(ROOT / "results" / "experiment_1" / "S1_controversial_call_high_density_W1.json")
    if not w0 or not w1:
        return

    from worldcup_causal_engine.reverse import diff_results

    diff = diff_results(w0, w1)
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.axis("off")
    text = (
        f"Fig.3 Trace diff: S1 W0 vs W1\n"
        f"fork_point: {diff.get('fork_point')}\n"
        f"W0 only: {' → '.join(diff.get('only_a', []))}\n"
        f"W1 only: {' → '.join(diff.get('only_b', []))}"
    )
    ax.text(0.05, 0.5, text, fontsize=11, family="monospace", va="center")
    fig.savefig(out_dir / "fig3_diff_trace.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "fig3_diff_trace.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_radar_per_scenario(scores: dict, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return

    per = scores.get("per_scenario", [])
    if not per:
        return

    n = len(per)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5), subplot_kw=dict(polar=True))
    if n == 1:
        axes = [axes]

    for ax, sc in zip(axes, per):
        dims = sc.get("dimensions", list(sc.get("kernel", {}).keys()))
        kernel = [sc.get("kernel", {}).get(d, 0) for d in dims]
        llm = [sc.get("llm", {}).get(d, 0) for d in dims]
        angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
        kernel += kernel[:1]
        llm += llm[:1]
        angles += angles[:1]
        ax.plot(angles, kernel, "o-", label="Kernel")
        ax.plot(angles, llm, "o-", label="LLM")
        ax.set_xticks(angles[:-1], [d[:12] for d in dims], size=7)
        ax.set_ylim(0, 1)
        sid = sc.get("scenario_id", "?")[:18]
        ax.set_title(sid)

    fig.suptitle("Fig.6b Per-scenario explainability (Kernel vs LLM)")
    fig.legend(loc="upper right", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(out_dir / "fig6b_radar_per_scenario.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_radar(scores: dict, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        _write_json_fallback(out_dir / "fig6_radar.json", scores)
        return

    dims = scores.get("dimensions", list(scores.get("kernel", {}).keys()))
    kernel = [scores.get("kernel", {}).get(d, 0) for d in dims]
    llm = [scores.get("llm", {}).get(d, 0) for d in dims]
    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    kernel += kernel[:1]
    llm += llm[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.plot(angles, kernel, "o-", label="Kernel")
    ax.fill(angles, kernel, alpha=0.15)
    ax.plot(angles, llm, "o-", label="LLM baseline")
    ax.fill(angles, llm, alpha=0.15)
    ax.set_xticks(angles[:-1], [d.replace("_", "\n") for d in dims], size=8)
    ax.set_ylim(0, 1)
    ax.set_title("Fig.6 Explainability radar (RQ4)")
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    fig.savefig(out_dir / "fig6_explainability_radar.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "fig6_explainability_radar.pdf", bbox_inches="tight")
    plt.close(fig)


def write_mechanism_graph(out_dir: Path) -> None:
    content = """digraph chain_a {
  rankdir=TB;
  node [shape=box, style=rounded];
  controversial_call -> viral_clip_published -> media_blame_frame -> rumor_amplified;
  rumor_amplified -> offline_mood_shift -> opposing_fans_contact -> verbal_conflict;
  controversial_call [label="controversial_call\\nsets: CONTROVERSIAL_CALL_VISIBLE"];
  viral_clip_published [label="viral_clip_published\\nwaits: CONTROVERSIAL_CALL_VISIBLE\\nresources: media_attention_budget"];
  media_blame_frame [label="media_blame_frame\\nsets: MEDIA_OUTRAGE_FRAME_ACTIVE"];
  rumor_amplified [label="rumor_amplified\\nwaits: MEDIA_OUTRAGE_FRAME_ACTIVE"];
}
"""
    (out_dir / "fig2_mechanism_chain.dot").write_text(content, encoding="utf-8")
    (out_dir / "fig2_mechanism_chain.mmd").write_text(
        """flowchart TB
  CC[controversial_call] --> VC[viral_clip_published]
  VC --> MB[media_blame_frame]
  MB --> RA[rumor_amplified]
  RA --> OM[offline_mood_shift]
  OM --> OF[opposing_fans_contact]
  OF --> VF[verbal_conflict]
""",
        encoding="utf-8",
    )


def export_tables(out_dir: Path) -> None:
    tables = out_dir.parent / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    exp1 = _load_json(ROOT / "results" / "experiment_1" / "summary.json")
    if exp1:
        lines = ["scenario,world,verbal,scuffle,panic,riot"]
        for r in exp1.get("results", []):
            fr = r.get("final_risk", {})
            lines.append(
                f"{r['scenario_id']},{r['world_id']},"
                f"{fr.get('verbal_conflict',0)},{fr.get('scuffle',0)},"
                f"{fr.get('panic',0)},{fr.get('riot',0)}"
            )
        (tables / "table2_pressure_test.csv").write_text("\n".join(lines), encoding="utf-8")

    abl = _load_json(ROOT / "results" / "experiment_2" / "ablation_summary.json")
    if abl:
        lines = ["scenario,ablation,verbal,blocked,path_length,has_trace"]
        for r in abl.get("results", []):
            lines.append(
                f"{r['scenario_id']},{r['ablation_id']},"
                f"{r.get('final_verbal_conflict_risk',0)},"
                f"{r.get('blocked_events_count',0)},"
                f"{r.get('path_length',0)},"
                f"{r.get('has_trace', True)}"
            )
        (tables / "table3_ablation.csv").write_text("\n".join(lines), encoding="utf-8")

    scores = _load_json(ROOT / "results" / "experiment_3" / "explainability_scores.json")
    if scores:
        lines = ["dimension,kernel,llm"]
        for d in scores.get("dimensions", []):
            lines.append(
                f"{d},{scores.get('kernel',{}).get(d,0)},{scores.get('llm',{}).get(d,0)}"
            )
        (tables / "table4_explainability.csv").write_text("\n".join(lines), encoding="utf-8")

    (tables / "table1_scenarios.csv").write_text(
        "id,description,trigger\n"
        "S1,Controversial call + high density,controversial_call@70\n"
        "S2,Team eliminated + transit delay,team_eliminated@88\n"
        "S3,Heat + crowd + comm delay,match_end@90\n",
        encoding="utf-8",
    )


def _write_json_fallback(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", default="paper/figures")
    args = parser.parse_args()

    out_dir = ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    write_mechanism_graph(out_dir)
    plot_diff_trace(out_dir)

    exp1 = _load_json(ROOT / "results" / "experiment_1" / "summary.json")
    if exp1:
        plot_risk_heatmap(exp1, out_dir)

    abl = _load_json(ROOT / "results" / "experiment_2" / "ablation_summary.json")
    if abl:
        plot_ablation(abl, out_dir)

    scores = _load_json(ROOT / "paper" / "figures" / "explainability_radar_merged.json")
    if not scores:
        scores = _load_json(ROOT / "paper" / "figures" / "explainability_radar.json")
    if not scores:
        scores = _load_json(ROOT / "results" / "experiment_3_zhisuan" / "explainability_scores_merged.json")
    if not scores:
        scores = _load_json(ROOT / "results" / "experiment_3" / "explainability_scores.json")
    if scores:
        plot_radar(scores, out_dir)
        if scores.get("per_scenario"):
            plot_radar_per_scenario(scores, out_dir)

    export_tables(out_dir)
    print(f"Figures/tables written to {out_dir} and paper/tables/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
