"""Strict JSON schema for LLM baseline output (matches Kernel result shape)."""

OUTPUT_SCHEMA = {
    "final_risk": {
        "verbal_conflict": "float 0-1",
        "scuffle": "float 0-1",
        "riot": "float 0-1",
        "panic": "float 0-1",
    },
    "dominant_path": ["event_kind_string", "..."],
    "active_flags": ["FLAG_NAME", "..."],
    "resource_bottlenecks": [{"resource": "name", "failures": 0}],
    "best_cut_points": [{"intervention": "kind", "before": "event_kind"}],
    "reasoning": "string explaining chain step-by-step; mention any event that did NOT occur and why",
}

SCHEMA_EXAMPLE = """{
  "final_risk": {
    "verbal_conflict": 0.52,
    "scuffle": 0.12,
    "riot": 0.0,
    "panic": 0.0
  },
  "dominant_path": [
    "controversial_call",
    "media_blame_frame",
    "rumor_amplified",
    "opposing_fans_contact",
    "verbal_conflict"
  ],
  "active_flags": [
    "MEDIA_OUTRAGE_FRAME_ACTIVE",
    "RUMOR_SPIKE"
  ],
  "resource_bottlenecks": [
    {"resource": "official_comm_channel", "failures": 1}
  ],
  "best_cut_points": [
    {"intervention": "official_clarification", "before": "rumor_amplified"}
  ],
  "reasoning": "Step-by-step causal chain. If an event did not occur, explain why (e.g. blocked by missing flag or resource)."
}"""

PROMPT_TEMPLATE = """You are simulating a World Cup crowd-risk CAUSAL ENGINE (not predicting real events).

Given scenario constraints, mechanism priors, and intervention world, output ONE JSON object.

RULES:
1. Output ONLY valid JSON. No markdown. No prose outside JSON.
2. Use EXACTLY the schema below. Do not rename fields. Do not use nested objects for resource_bottlenecks.
3. dominant_path MUST be an array of mechanism event kind strings (snake_case), NOT a single string.
4. final_risk values MUST be floats between 0.0 and 1.0 (not "high"/"low").
5. active_flags MUST use UPPER_SNAKE_CASE flag names from the mechanism spec when possible.
6. resource_bottlenecks: list of {{"resource": "<name>", "failures": <int>}} only.
7. If official_comm_channel is 0 in resources, include it in resource_bottlenecks.
8. In reasoning, explain step-by-step AND mention at least one event that did NOT happen and why.
9. Compare W0 vs W1: if intervention world, dominant_path or final_risk should differ from baseline.

Valid event kinds include:
  controversial_call, viral_clip_published, media_blame_frame, rumor_amplified,
  offline_mood_shift, opposing_fans_contact, verbal_conflict,
  team_eliminated, fans_gather, match_end, transit_delay, crowd_density_spike,
  panic_signal, official_clarification

Valid flags include:
  CONTROVERSIAL_CALL_VISIBLE, MEDIA_OUTRAGE_FRAME_ACTIVE, RUMOR_SPIKE,
  OPPOSING_FANS_COLOCATED, CROWD_DENSITY_HIGH, TRANSIT_DELAY_ACTIVE,
  POLICE_TRUST_LOW, HEAT_STRESS_HIGH

Schema example:
{schema_example}

Scenario JSON:
{scenario_json}

Intervention world JSON:
{world_json}

Mechanism priors (summary):
{priors_summary}
"""
