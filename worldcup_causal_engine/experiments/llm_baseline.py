"""LLM baseline comparison with rule-based mock when no API key."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

from worldcup_causal_engine.experiments.llm_schema import PROMPT_TEMPLATE, SCHEMA_EXAMPLE
from worldcup_causal_engine.experiments.runner import resolve_scenario_path
from worldcup_causal_engine.experiments.scoring import compare_explainability
from worldcup_causal_engine.scenarios import _project_root, load_intervention, load_priors, load_scenario, run_scenario

def _priors_summary(priors: dict[str, Any]) -> str:
    lines = []
    for mech, params in list(priors.items())[:8]:
        lines.append(f"{mech}: {params}")
    return "\n".join(lines)


def _validate_output(data: dict[str, Any]) -> dict[str, Any]:
    required = ["final_risk", "dominant_path", "active_flags", "resource_bottlenecks", "best_cut_points", "reasoning"]
    for key in required:
        data.setdefault(key, [] if key not in ("final_risk", "reasoning") else {})
    if isinstance(data.get("reasoning"), dict):
        data["reasoning"] = json.dumps(data["reasoning"])
    if isinstance(data.get("final_risk"), str):
        level = data["final_risk"].lower()
        mapping = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 0.95}
        v = mapping.get(level, 0.5)
        data["final_risk"] = {
            "verbal_conflict": v,
            "scuffle": round(v * 0.6, 2),
            "riot": round(v * 0.2, 2),
            "panic": round(v * 0.15, 2),
        }
    dp = data.get("dominant_path")
    if isinstance(dp, str):
        for sep in ("->", "→", "->", " then "):
            if sep in dp:
                data["dominant_path"] = [s.strip() for s in dp.split(sep) if s.strip()]
                break
        else:
            data["dominant_path"] = [dp.strip()] if dp.strip() else []
    bn = data.get("resource_bottlenecks", [])
    if isinstance(bn, dict):
        data["resource_bottlenecks"] = [
            {"resource": k, "failures": 1, "detail": v}
            for k, v in bn.items()
        ]
    elif isinstance(bn, list):
        normalized = []
        for item in bn:
            if isinstance(item, str):
                res = item.split("(")[0].split(":")[0].strip()
                normalized.append({"resource": res, "failures": 1})
            elif isinstance(item, dict):
                res = item.get("resource", "unknown")
                if isinstance(res, str):
                    res = res.split("(")[0].split(":")[0].strip()
                normalized.append({"resource": res, "failures": int(item.get("failures", 1))})
        data["resource_bottlenecks"] = normalized
    cps = data.get("best_cut_points", [])
    if isinstance(cps, list):
        norm_cps = []
        for item in cps:
            if isinstance(item, dict):
                norm_cps.append({
                    "intervention": item.get("intervention") or item.get("action") or item.get("event", ""),
                    "before": item.get("before") or item.get("stage") or item.get("event", ""),
                })
        data["best_cut_points"] = norm_cps
    if isinstance(data.get("active_flags"), list):
        data["active_flags"] = [
            str(f).upper().replace(" ", "_").split("(")[0].strip()
            for f in data["active_flags"]
        ]
    fr = data.get("final_risk", {})
    if isinstance(fr, dict):
        for k in ("verbal_conflict", "scuffle", "riot", "panic"):
            if k in fr:
                try:
                    fr[k] = max(0.0, min(1.0, float(fr[k])))
                except (TypeError, ValueError):
                    fr[k] = 0.5
    return data


def mock_llm_response(
    scenario: dict[str, Any],
    world_id: str,
    interventions: list[dict[str, Any]],
    priors: dict[str, Any],
    run_id: int = 0,
) -> dict[str, Any]:
    """Deterministic rule-based baseline simulating LLM output."""
    trigger = scenario.get("trigger") or (scenario.get("triggers") or [{}])[0]
    kind = trigger.get("kind", "unknown")
    rng_jitter = (run_id % 3) * 0.02

    path_map = {
        "controversial_call": [
            "controversial_call", "media_blame_frame", "rumor_amplified",
            "opposing_fans_contact", "verbal_conflict",
        ],
        "team_eliminated": [
            "team_eliminated", "fans_gather", "bar_district_pressure", "verbal_conflict",
        ],
        "match_end": [
            "match_end", "fans_gather", "transit_delay", "crowd_density_spike", "panic_signal",
        ],
    }
    dominant_path = path_map.get(kind, [kind, "fans_gather", "verbal_conflict"])
    if world_id == "W1":
        dominant_path = dominant_path[:3] + ["official_clarification"]

    resources = scenario.get("resources", {})
    bottlenecks = []
    if resources.get("official_comm_channel", 5) == 0:
        bottlenecks.append({"resource": "official_comm_channel", "failures": 1})

    verbal = 0.55 + rng_jitter
    if world_id == "W1":
        verbal = max(0.1, verbal - 0.25)

    return _validate_output({
        "final_risk": {
            "verbal_conflict": round(verbal, 2),
            "scuffle": round(0.2 + rng_jitter, 2),
            "riot": 0.05,
            "panic": 0.1 if kind == "match_end" else 0.05,
        },
        "dominant_path": dominant_path,
        "active_flags": ["MEDIA_OUTRAGE_FRAME_ACTIVE"] if kind == "controversial_call" else ["TEAM_ELIMINATED"],
        "resource_bottlenecks": bottlenecks,
        "best_cut_points": [
            {"intervention": "official_clarification", "before": "rumor_amplified"},
        ] if world_id == "W1" else [],
        "reasoning": (
            f"Trigger {kind} elevates outrage; social amplification leads to "
            f"offline contact. Intervention {world_id} may reduce rumor spread."
        ),
        "source": "mock_llm",
        "run_id": run_id,
    })


def call_chat_api(
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """OpenAI-compatible chat completions (OpenAI / 智算 ai.azya.top / etc.)."""
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY")
    if not api_key:
        raise RuntimeError("API key not set (OPENAI_API_KEY or ZHISUAN_API_KEY)")

    base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Respond with valid JSON only. No markdown fences."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
    return _validate_output(json.loads(content))


def call_openai_api(prompt: str, model: str = "gpt-4o-mini") -> dict[str, Any]:
    return call_chat_api(prompt, model=model)


def list_models(
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[str]:
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY")
    base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(
        f"{base}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return sorted(m.get("id", "") for m in payload.get("data", []) if m.get("id"))


def run_llm_baseline(
    scenario_name: str,
    worlds: list[str] | None = None,
    runs: int = 5,
    output_dir: str | Path | None = None,
    use_api: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    worlds = worlds or ["W0", "W1"]
    out_root = Path(output_dir) if output_dir else _project_root() / "results" / "experiment_3"
    (out_root / "llm").mkdir(parents=True, exist_ok=True)

    scenario_path = resolve_scenario_path(scenario_name)
    scenario = load_scenario(scenario_path)
    priors = load_priors()
    priors_summary = _priors_summary(priors)

    all_llm: dict[str, list[dict[str, Any]]] = {}
    kernel_results: dict[str, dict[str, Any]] = {}

    for world_id in worlds:
        kernel_results[world_id] = run_scenario(scenario_path, world_id=world_id)
        interventions = load_intervention(world_id)
        world_json = json.dumps({"world_id": world_id, "interventions": interventions})
        scenario_json = json.dumps({
            "scenario_id": scenario["scenario_id"],
            "trigger": scenario.get("trigger"),
            "triggers": scenario.get("triggers"),
            "context": scenario.get("context"),
            "resources": scenario.get("resources"),
        })

        prompt = PROMPT_TEMPLATE.format(
            schema_example=SCHEMA_EXAMPLE,
            scenario_json=scenario_json,
            world_json=world_json,
            priors_summary=priors_summary,
        )

        llm_runs: list[dict[str, Any]] = []
        for i in range(runs):
            try:
                key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY")
                if use_api and key:
                    out = call_chat_api(
                        prompt,
                        model=model,
                        api_key=key,
                        base_url=base_url,
                    )
                    out["source"] = "api"
                    out["api_base"] = base_url or os.environ.get("OPENAI_BASE_URL", "")
                    out["model"] = model or os.environ.get("OPENAI_MODEL", "")
                else:
                    out = mock_llm_response(scenario, world_id, interventions, priors, run_id=i)
            except Exception as exc:
                out = mock_llm_response(scenario, world_id, interventions, priors, run_id=i)
                out["fallback_reason"] = str(exc)

            out["world_id"] = world_id
            out["scenario_id"] = scenario["scenario_id"]
            llm_runs.append(out)
            fname = f"llm/{scenario['scenario_id']}_{world_id}_run{i}.json"
            (out_root / fname).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

        all_llm[world_id] = llm_runs

    scores = compare_explainability(
        kernel_results.get("W0", {}),
        kernel_results.get("W1", {}),
        all_llm.get("W0", []),
        all_llm.get("W1", []),
        scenario.get("resources"),
    )
    scores["scenario_id"] = scenario["scenario_id"]
    scores["llm_source"] = (
        "api" if use_api and (api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ZHISUAN_API_KEY"))
        else "mock"
    )
    if model or os.environ.get("OPENAI_MODEL"):
        scores["llm_model"] = model or os.environ.get("OPENAI_MODEL")
    if base_url or os.environ.get("OPENAI_BASE_URL"):
        scores["api_base"] = base_url or os.environ.get("OPENAI_BASE_URL")

    score_path = out_root / f"explainability_scores_{scenario['scenario_id']}.json"
    score_path.write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_root / "explainability_scores.json").write_text(
        json.dumps(scores, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (_project_root() / "paper" / "figures").mkdir(parents=True, exist_ok=True)
    (_project_root() / "paper" / "figures" / "explainability_radar.json").write_text(
        json.dumps(scores, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return scores


def merge_explainability_scores(score_files: list[Path]) -> dict[str, Any]:
    """Average kernel/llm dimension scores across scenarios."""
    loaded = []
    for p in score_files:
        if p.exists():
            loaded.append(json.loads(p.read_text(encoding="utf-8")))
    if not loaded:
        return {}

    dims = loaded[0].get("dimensions", list(loaded[0].get("kernel", {}).keys()))
    merged: dict[str, Any] = {
        "scenarios": [s.get("scenario_id") for s in loaded],
        "dimensions": dims,
        "kernel": {},
        "llm": {},
        "per_scenario": loaded,
    }
    for d in dims:
        merged["kernel"][d] = round(sum(s.get("kernel", {}).get(d, 0) for s in loaded) / len(loaded), 4)
        merged["llm"][d] = round(sum(s.get("llm", {}).get(d, 0) for s in loaded) / len(loaded), 4)
    merged["llm_source"] = loaded[0].get("llm_source", "unknown")
    merged["llm_model"] = loaded[0].get("llm_model", "")
    merged["api_base"] = loaded[0].get("api_base", "")
    return merged


def run_llm_baseline_batch(
    scenarios: list[str],
    worlds: list[str] | None = None,
    runs: int = 5,
    output_dir: str | Path | None = None,
    use_api: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    out_root = Path(output_dir) if output_dir else _project_root() / "results" / "experiment_3_zhisuan"
    score_files: list[Path] = []
    for sc in scenarios:
        run_llm_baseline(
            sc, worlds=worlds, runs=runs, output_dir=out_root,
            use_api=use_api, api_key=api_key, base_url=base_url, model=model,
        )
        sid = resolve_scenario_path(sc)
        scenario = load_scenario(sid)
        score_files.append(out_root / f"explainability_scores_{scenario['scenario_id']}.json")

    merged = merge_explainability_scores(score_files)
    (out_root / "explainability_scores_merged.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    fig_dir = _project_root() / "paper" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    (fig_dir / "explainability_radar_merged.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (fig_dir / "explainability_radar.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM baseline comparison")
    parser.add_argument("--scenario", default="S1")
    parser.add_argument("--worlds", default="W0,W1")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", default="results/experiment_3")
    parser.add_argument("--use-api", action="store_true")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL, e.g. https://ai.azya.top/v1")
    parser.add_argument("--api-key", default=None, help="API key (prefer env ZHISUAN_API_KEY)")
    parser.add_argument("--model", default=None, help="Model id")
    parser.add_argument("--list-models", action="store_true", help="List available models and exit")
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run S1 and S3 and merge explainability scores",
    )
    args = parser.parse_args(argv)

    if args.list_models:
        models = list_models(api_key=args.api_key, base_url=args.base_url)
        print(json.dumps(models, indent=2, ensure_ascii=False))
        return 0

    worlds = [w.strip() for w in args.worlds.split(",")]

    if args.all_scenarios:
        merged = run_llm_baseline_batch(
            ["S1", "S3"],
            worlds=worlds,
            runs=args.runs,
            output_dir=args.output,
            use_api=args.use_api,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
        )
        print(json.dumps(merged, indent=2))
        print(f"Merged scores → {args.output}/explainability_scores_merged.json", file=sys.stderr)
        return 0

    scores = run_llm_baseline(
        args.scenario,
        worlds=worlds,
        runs=args.runs,
        output_dir=args.output,
        use_api=args.use_api,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )
    print(json.dumps(scores, indent=2))
    print(f"Saved to {args.output}/explainability_scores.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
