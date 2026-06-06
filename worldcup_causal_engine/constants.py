"""State variables, flags, and default resource pools."""

from __future__ import annotations

# --- State keys ---

STATE_KEYS = [
    "match_tension",
    "rivalry_intensity",
    "perceived_unfairness",
    "humiliation_level",
    "media_attention",
    "outrage_frame",
    "blame_frame",
    "rumor_volume",
    "misinfo_confidence",
    "platform_velocity",
    "crowd_density",
    "fan_zone_pressure",
    "transit_pressure",
    "heat_stress",
    "police_visibility",
    "police_trust",
    "deescalation_capacity",
    "verbal_conflict_risk",
    "scuffle_risk",
    "riot_risk",
    "panic_risk",
]

RISK_KEYS = [
    "verbal_conflict_risk",
    "scuffle_risk",
    "riot_risk",
    "panic_risk",
]

# --- Flags ---

MATCH_HIGH_TENSION = "MATCH_HIGH_TENSION"
CONTROVERSIAL_CALL_VISIBLE = "CONTROVERSIAL_CALL_VISIBLE"
TEAM_ELIMINATED = "TEAM_ELIMINATED"
MEDIA_OUTRAGE_FRAME_ACTIVE = "MEDIA_OUTRAGE_FRAME_ACTIVE"
RUMOR_SPIKE = "RUMOR_SPIKE"
OPPOSING_FANS_COLOCATED = "OPPOSING_FANS_COLOCATED"
CROWD_DENSITY_HIGH = "CROWD_DENSITY_HIGH"
POLICE_TRUST_LOW = "POLICE_TRUST_LOW"
TRANSIT_DELAY_ACTIVE = "TRANSIT_DELAY_ACTIVE"
HEAT_STRESS_HIGH = "HEAT_STRESS_HIGH"
DEESCALATION_ACTIVE = "DEESCALATION_ACTIVE"
FAN_FLOWS_SEPARATED = "FAN_FLOWS_SEPARATED"

ALL_FLAGS = {
    MATCH_HIGH_TENSION,
    CONTROVERSIAL_CALL_VISIBLE,
    TEAM_ELIMINATED,
    MEDIA_OUTRAGE_FRAME_ACTIVE,
    RUMOR_SPIKE,
    OPPOSING_FANS_COLOCATED,
    CROWD_DENSITY_HIGH,
    POLICE_TRUST_LOW,
    TRANSIT_DELAY_ACTIVE,
    HEAT_STRESS_HIGH,
    DEESCALATION_ACTIVE,
    FAN_FLOWS_SEPARATED,
}

SCENARIO_FILES = {
    "S1": "S1_controversial_call_high_density.json",
    "S2": "S2_team_eliminated_transit_delay.json",
    "S3": "S3_heat_crowd_comm_delay.json",
    "S4": "S4_misleading_viral_clip.json",
    "S5": "S5_post_match_transit_delay.json",
    "S6": "S6_heat_fanzone_overflow.json",
}

WORLD_IDS = ["W0", "W1", "W2", "W3", "W4", "W5", "W6"]

# --- Resources ---

DEFAULT_RESOURCES = {
    "media_attention_budget": 100,
    "official_comm_channel": 5,
    "fact_check_capacity": 20,
    "police_units": 100,
    "deescalation_teams": 20,
    "medical_units": 30,
    "transport_capacity": 1000,
    "fan_zone_capacity": 800,
}


def default_state() -> dict[str, float]:
    return {key: 0.0 for key in STATE_KEYS}


def default_state_with_baseline() -> dict[str, float]:
    state = default_state()
    state["police_trust"] = 0.5
    state["deescalation_capacity"] = 0.5
    return state
