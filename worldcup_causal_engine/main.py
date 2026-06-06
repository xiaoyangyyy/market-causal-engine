"""CLI entry point for single scenario runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from worldcup_causal_engine.constants import WORLD_IDS
from worldcup_causal_engine.reverse import analyze_result, diff_results
from worldcup_causal_engine.scenarios import run_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="World Cup causal engine — scenario runner with reverse debugger"
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Path to scenario JSON file",
    )
    parser.add_argument(
        "--world",
        default="W0",
        choices=WORLD_IDS,
        help="Intervention world (W0=baseline)",
    )
    parser.add_argument(
        "--until",
        type=int,
        default=120,
        help="Simulation end time (match minutes)",
    )
    parser.add_argument(
        "--output",
        help="Write result JSON to this file",
    )
    parser.add_argument(
        "--priors",
        help="Path to mechanism priors JSON",
    )
    parser.add_argument(
        "--priors-profile",
        choices=["v0.1", "calibrated"],
        default="v0.1",
        help="Priors profile: v0.1 (default) or calibrated (Qatar 2022 post-hoc)",
    )
    parser.add_argument(
        "--scenario-specific-priors",
        action="store_true",
        help="With calibrated profile: use per-scenario overrides from calibration reports",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print reverse-debugger explanation to stderr",
    )
    parser.add_argument(
        "--diff-against",
        metavar="WORLD",
        help="Compare trace against another world (e.g. W0)",
    )
    parser.add_argument(
        "--feed",
        help="Path to JSONL atom feed for text-driven mode",
    )
    parser.add_argument(
        "--ledger-output",
        help="Write evidence ledger JSON to this file",
    )
    parser.add_argument(
        "--match-id",
        default="M12",
        help="Match id used in cluster keys",
    )
    parser.add_argument(
        "--propose-demo",
        action="store_true",
        help="LLM proposes official_clarification; kernel verifies (Phase 5 demo)",
    )
    parser.add_argument(
        "--fork-demo",
        action="store_true",
        help="Fork baseline at rumor_amplified + W1 vs full W1 (Phase 6 demo)",
    )
    parser.add_argument(
        "--mdg",
        action="store_true",
        help="Output event-level MDG JSON for this run (Phase 7)",
    )
    parser.add_argument(
        "--mdg-mermaid-output",
        help="Write event-level MDG as Mermaid flowchart (.mmd)",
    )
    parser.add_argument(
        "--llm-propose-demo",
        action="store_true",
        help="LLM proposes one intervention; kernel verifies (mock or --use-api)",
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use OpenAI-compatible API for --llm-propose-demo",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model (default: OPENAI_MODEL env or qwen3.5)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL (default: OPENAI_BASE_URL env)",
    )
    parser.add_argument(
        "--proposal-max-retries",
        type=int,
        default=3,
        help="Max LLM proposal attempts with VM feedback (default: 3)",
    )
    args = parser.parse_args(argv)

    if args.fork_demo:
        from worldcup_causal_engine.ledger.fork import replay_fork_from_scenario

        _base, fork, full = replay_fork_from_scenario(
            args.scenario,
            baseline_world="W0",
            fork_before_kind="rumor_amplified",
            intervention_world="W1",
            until=args.until,
        )
        payload = {
            "fork": fork.to_dict(),
            "full_w1": {"dominant_path": full["dominant_path"], "final_risk": full["final_risk"]},
            "equivalent": fork.dominant_path == full["dominant_path"]
            and fork.final_risk == full["final_risk"],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.llm_propose_demo:
        from worldcup_causal_engine.scenarios import run_llm_propose_demo

        result = run_llm_propose_demo(
            args.scenario,
            until=args.until,
            use_api=args.use_api,
            base_url=args.base_url,
            model=args.model,
            max_attempts=args.proposal_max_retries,
        )
        output_text = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(output_text, encoding="utf-8")
        else:
            print(output_text)
        vr = result.get("proposal_verification", {})
        raw = result.get("llm_raw", {})
        attempts = result.get("proposal_attempts", [])
        effect = result.get("intervention_effect", {})
        print(
            f"\n--- LLM Proposal ({raw.get('source', 'unknown')}) ---\n"
            f"  attempts: {len(attempts)}\n"
            f"  kind: {result.get('llm_proposal', {}).get('kind')}\n"
            f"  accepted: {vr.get('accepted')}\n"
            f"  reason: {vr.get('reason_code')} — {vr.get('detail')}\n"
            f"  improved vs W0: {effect.get('improved')}",
            file=sys.stderr,
        )
        return 0

    if args.propose_demo:
        from worldcup_causal_engine.scenarios import run_proposal_demo

        result = run_proposal_demo(args.scenario, until=args.until)
        output_text = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(output_text, encoding="utf-8")
        else:
            print(output_text)
        vr = result.get("proposal_verification", {})
        print(
            f"\n--- Proposal Verification ---\n  accepted: {vr.get('accepted')}\n  reason: {vr.get('reason_code')} — {vr.get('detail')}",
            file=sys.stderr,
        )
        return 0

    result = run_scenario(
        scenario_path=args.scenario,
        world_id=args.world,
        until=args.until,
        priors_path=args.priors,
        priors_profile=None if args.priors else args.priors_profile,
        scenario_specific_priors=args.scenario_specific_priors,
        feed_path=args.feed,
        match_id=args.match_id,
        ledger_output=args.ledger_output,
    )
    if args.mdg or args.mdg_mermaid_output:
        from worldcup_causal_engine.mdg.builder import build_event_mdg_from_result
        from worldcup_causal_engine.mdg.export import export_mermaid_file

        mdg = build_event_mdg_from_result(result)
        result["event_mdg"] = mdg.to_dict()
        if args.mdg_mermaid_output:
            mmd_path = export_mermaid_file(
                mdg,
                args.mdg_mermaid_output,
                title=f"{result.get('scenario_id', '')} {result.get('world_id', '')}",
            )
            print(f"Wrote MDG mermaid to {mmd_path}", file=sys.stderr)

    if args.diff_against:
        baseline = run_scenario(
            scenario_path=args.scenario,
            world_id=args.diff_against,
            until=args.until,
            priors_path=args.priors,
            priors_profile=None if args.priors else args.priors_profile,
            scenario_specific_priors=args.scenario_specific_priors,
            feed_path=args.feed,
            match_id=args.match_id,
        )
        result["diff_trace"] = diff_results(baseline, result)

    output_text = json.dumps(result, indent=2, ensure_ascii=False)

    if result.get("ledger_path"):
        print(f"Wrote ledger to {result['ledger_path']}", file=sys.stderr)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Wrote result to {out_path}", file=sys.stderr)
    else:
        print(output_text)

    debugger = analyze_result(result)
    path = debugger.dominant_risk_path() or result.get("dominant_path", [])

    print("\n--- Dominant Risk Path ---", file=sys.stderr)
    print(" → ".join(path), file=sys.stderr)
    print("\n--- Final Risk ---", file=sys.stderr)
    for key, value in result["final_risk"].items():
        print(f"  {key}: {value}", file=sys.stderr)

    if result.get("evidence_ledger"):
        print("\n--- Evidence Ledger ---", file=sys.stderr)
        ledger = result["evidence_ledger"]
        print(f"  atoms: {ledger.get('total_atoms')}  clusters: {ledger.get('total_clusters')}  compiled: {ledger.get('compiled_clusters')}", file=sys.stderr)

    if args.explain:
        print("\n" + debugger.explain(
            scenario_id=result.get("scenario_id", ""),
            world_id=result.get("world_id", ""),
        ), file=sys.stderr)

    if args.diff_against and "diff_trace" in result:
        diff = result["diff_trace"]
        print("\n--- Trace Diff ---", file=sys.stderr)
        print(f"  fork_point: {diff.get('fork_point')}", file=sys.stderr)
        print(f"  only_{args.world}: {' → '.join(diff.get('only_b', []))}", file=sys.stderr)
        print(f"  only_{args.diff_against}: {' → '.join(diff.get('only_a', []))}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
