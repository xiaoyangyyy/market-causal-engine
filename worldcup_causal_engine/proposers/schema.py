"""LLM proposal schema — proposals only, never direct kernel commits."""

from __future__ import annotations

import json
from typing import Any

PROPOSAL_SCHEMA_EXAMPLE = """{
  "kind": "official_clarification",
  "time": 87,
  "priority": 0,
  "payload": {"topic": "controversial_call", "credibility": 0.7},
  "confidence": 0.85,
  "reasoning": "Rumor spike active; official channel available; clarify before mood shift."
}"""

PROPOSAL_PROMPT_TEMPLATE = """You are a World Cup crowd-risk intervention proposer.
You MUST output ONE JSON object only (no markdown). You propose interventions; the causal kernel verifies and executes.

Scenario:
{scenario_json}

Current kernel state at checkpoint (minute ~{checkpoint_minute}):
{state_json}

Active flags: {flags}
Remaining resources: {resources}

=== Engine causal analysis (W0 baseline) ===
Dominant risk path: {dominant_path}
Baseline final risk: {baseline_risk}
Resource bottlenecks: {resource_bottlenecks}
Event schedule (scenario triggers): {event_schedule}
Optimal intervention minutes (engine): {intervention_timing}
Best cut points (from engine intervention sweep):
{best_cut_points}
Recommended interventions (ranked): {recommended_interventions}
Scenario-specific hints:
{scenario_hints}

Allowed intervention kinds (pick ONE):
official_clarification, team_captain_message, separate_fan_flows, transit_reroute, deploy_deescalation, platform_rumor_throttle

Output schema:
{schema_example}

Rules:
1. Propose only ONE intervention with kind, time (match minute), priority (0=highest), payload.
2. If official_comm_channel is 0, do NOT propose official_clarification.
3. time must be >= {checkpoint_minute} and <= 119.
4. Verification uses state at (time - 1): official_clarification requires rumor_volume > 0 at that moment (typically time >= 87 after rumor_amplified).
5. If misinfo_confidence > 0.5, strongly prefer platform_rumor_throttle over official_clarification.
6. For transit/panic chains: transit_reroute must be AFTER transit_delay fires (delay_minute+1..+3), never same minute as transit_delay.
7. If optimal intervention minutes lists transit_reroute, use that exact time.
8. confidence in [0,1]; reasoning one sentence.
{retry_feedback}
"""


def format_retry_feedback(rejections: list[dict[str, Any]]) -> str:
    if not rejections:
        return ""
    lines = ["\n=== Previous proposal(s) REJECTED — revise and try again ==="]
    for i, rej in enumerate(rejections, 1):
        lines.append(
            f"Attempt {i}: kind={rej.get('kind')} time={rej.get('time')} "
            f"reason={rej.get('reason_code')} detail={rej.get('detail')}"
        )
        if rej.get("reason_code") == "pre_condition":
            lines.append("  Hint: delay proposal until rumor_volume > 0 (usually minute 88+).")
        if rej.get("reason_code") == "resource_shortage":
            lines.append("  Hint: pick an intervention that does not need the exhausted resource.")
        if rej.get("reason_code") == "proposal_too_late":
            lines.append("  Hint: propose a future minute >= current checkpoint.")
        if rej.get("reason_code") == "ineffective_intervention":
            if rej.get("kind") == "transit_reroute":
                lines.append(
                    "  Hint: transit_reroute timing wrong — move to AFTER transit_delay "
                    "(use intervention_timing.transit_reroute, typically delay+3)."
                )
            else:
                lines.append(
                    "  Hint: proposal passed VM but did not reduce baseline risk — "
                    "try a different kind from best_cut_points."
                )
    return "\n".join(lines) + "\n"


def build_proposal_prompt(
    scenario: dict[str, Any],
    kernel: Any,
    context: dict[str, Any],
    *,
    rejections: list[dict[str, Any]] | None = None,
) -> str:
    baseline = context.get("baseline_w0", {})
    return PROPOSAL_PROMPT_TEMPLATE.format(
        scenario_json=json.dumps(
            {
                "scenario_id": scenario.get("scenario_id"),
                "triggers": scenario.get("triggers"),
                "trigger": scenario.get("trigger"),
                "context": scenario.get("context"),
                "resources": {
                    **scenario.get("resources", {}),
                    **scenario.get("resources_override", {}),
                },
                "initial_state": scenario.get("initial_state"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        checkpoint_minute=context.get("checkpoint_minute", 55),
        state_json=json.dumps(
            {k: round(v, 3) for k, v in kernel.state.items() if v > 0.01},
            ensure_ascii=False,
        ),
        flags=sorted(kernel.flags),
        resources={k: round(v, 1) for k, v in kernel.resources.items()},
        dominant_path=baseline.get("dominant_path", []),
        baseline_risk=baseline.get("final_risk", {}),
        resource_bottlenecks=baseline.get("resource_bottlenecks", []),
        event_schedule=json.dumps(context.get("event_schedule", {}), ensure_ascii=False),
        intervention_timing=json.dumps(context.get("intervention_timing", {}), ensure_ascii=False),
        best_cut_points=json.dumps(context.get("best_cut_points", []), ensure_ascii=False),
        recommended_interventions=context.get("recommended_interventions", []),
        scenario_hints="\n".join(f"- {h}" for h in context.get("scenario_hints", [])) or "- (none)",
        schema_example=PROPOSAL_SCHEMA_EXAMPLE,
        retry_feedback=format_retry_feedback(rejections or []),
    )
