"""Market state variables, flags, resources, and scenario registry."""

from __future__ import annotations

# --- State keys ---

STATE_KEYS = [
    "fundamental_expectation",
    "valuation_pressure",
    "investor_sentiment",
    "attention_intensity",
    "liquidity_depth",
    "volatility_state",
    "position_crowding",
    "short_interest_pressure",
    "option_gamma_exposure",
    "sector_risk",
    "macro_risk_appetite",
    "regulatory_risk",
    "trust_level",
    "bond_yield_pressure",
    "growth_value_tilt",
    "stock_beta_exposure",
    "directional_pressure_score",
    "volatility_risk_score",
    "liquidity_stress_score",
    "drawdown_risk_score",
]

OUTCOME_KEYS = [
    "directional_pressure_score",
    "volatility_risk_score",
    "liquidity_stress_score",
    "drawdown_risk_score",
]

OUTCOME_DISPLAY = {
    "directional_pressure_score": "directional_pressure",
    "volatility_risk_score": "volatility_risk",
    "liquidity_stress_score": "liquidity_stress",
    "drawdown_risk_score": "drawdown_risk",
}

# --- Flags ---

EARNINGS_RELEASED = "EARNINGS_RELEASED"
EARNINGS_MISS = "EARNINGS_MISS"
GUIDANCE_CUT = "GUIDANCE_CUT"
ANALYST_DOWNGRADE = "ANALYST_DOWNGRADE"
INSTITUTIONAL_REBALANCE = "INSTITUTIONAL_REBALANCE"
OPTION_GAMMA_ACTIVE = "OPTION_GAMMA_ACTIVE"
LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
RETAIL_ATTENTION_SPIKE = "RETAIL_ATTENTION_SPIKE"
MACRO_SHOCK_ACTIVE = "MACRO_SHOCK_ACTIVE"
SECTOR_SPILLOVER = "SECTOR_SPILLOVER"
SHORT_SQUEEZE_ACTIVE = "SHORT_SQUEEZE_ACTIVE"
ANALYST_DOWNGRADE_SUPPRESSED = "ANALYST_DOWNGRADE_SUPPRESSED"
SOCIAL_AMPLIFICATION_SUPPRESSED = "SOCIAL_AMPLIFICATION_SUPPRESSED"
OPTION_GAMMA_SUPPRESSED = "OPTION_GAMMA_SUPPRESSED"
SECTOR_SPILLOVER_SUPPRESSED = "SECTOR_SPILLOVER_SUPPRESSED"
MACRO_SHOCK_SUPPRESSED = "MACRO_SHOCK_SUPPRESSED"

ALL_FLAGS = {
    EARNINGS_RELEASED,
    EARNINGS_MISS,
    GUIDANCE_CUT,
    ANALYST_DOWNGRADE,
    INSTITUTIONAL_REBALANCE,
    OPTION_GAMMA_ACTIVE,
    LIQUIDITY_STRESS,
    RETAIL_ATTENTION_SPIKE,
    MACRO_SHOCK_ACTIVE,
    SECTOR_SPILLOVER,
    SHORT_SQUEEZE_ACTIVE,
    ANALYST_DOWNGRADE_SUPPRESSED,
    SOCIAL_AMPLIFICATION_SUPPRESSED,
    OPTION_GAMMA_SUPPRESSED,
    SECTOR_SPILLOVER_SUPPRESSED,
    MACRO_SHOCK_SUPPRESSED,
}

SCENARIO_FILES = {
    # MVP 1: Earnings
    "E1": "E1_earnings_guidance_cut.json",
    "E2": "E2_earnings_beat_sector_sympathy.json",
    # MVP 2: Short report
    "S1": "S1_short_report_cascade.json",
    "S2": "S2_short_report_regulatory_overhang.json",
    # MVP 3: Macro transmission
    "X1": "X1_fomc_rate_shock.json",
    "X2": "X2_cpi_rotation_beta.json",
    # Legacy aliases
    "M1": "E1_earnings_guidance_cut.json",
    "M2": "M2_analyst_downgrade_cascade.json",
    "M3": "S1_short_report_cascade.json",
    "M4": "X1_fomc_rate_shock.json",
}

DOMAIN_REGISTRY = {
    "earnings": {
        "label": "Earnings Event Causal Engine",
        "scenarios": ["E1", "E2"],
        "case_studies": ["nflx_2022q1_earnings", "snap_2022q3_earnings", "meta_2022q4_earnings", "shop_2022q2_earnings"],
        "inputs": [
            "earnings release",
            "earnings call transcript",
            "analyst rating changes",
            "intraday price/volume/volatility",
            "sector ETF movement",
            "ad revenue (digital)",
        ],
        "outputs": [
            "earnings_impact_path",
            "dominant_move_reason",
            "fundamental vs sentiment vs liquidity contributions",
            "calibrated return estimate",
            "counterfactual world comparison",
        ],
    },
    "short_report": {
        "label": "Short Seller Report Impact Engine",
        "scenarios": ["S1", "S2"],
        "case_studies": ["hindenburg_nikola_2020", "gme_2021_01_squeeze", "luckin_2020_fraud"],
        "inputs": [
            "short seller report",
            "company response",
            "news propagation",
            "social discussion",
            "short interest",
            "volume/volatility",
        ],
        "outputs": [
            "trust_impact_path",
            "liquidity_pressure",
            "regulatory_risk",
            "continuation vs reversal explanation",
        ],
    },
    "macro": {
        "label": "Macro Event Transmission Engine",
        "scenarios": ["X1", "X2"],
        "case_studies": ["fomc_2022_75bp", "cpi_2022_06_hot"],
        "inputs": [
            "CPI / FOMC / NFP",
            "bond yield reaction",
            "sector ETF movement",
            "growth/value rotation",
            "individual stock beta",
        ],
        "outputs": [
            "macro_transmission_path",
            "macro_to_sector_to_stock chain",
            "portfolio risk contribution",
        ],
    },
}

# Backward compat
MVP_GROUPS = DOMAIN_REGISTRY

SCENARIO_DOMAIN: dict[str, str] = {
    "E1_earnings_guidance_cut": "earnings",
    "E2_earnings_beat_sector_sympathy": "earnings",
    "M1_earnings_guidance_cut": "earnings",
    "M2_analyst_downgrade_cascade": "earnings",
    "case_nflx_2022q1_earnings": "earnings",
    "case_snap_2022q3_earnings": "earnings",
    "case_meta_2022q4_earnings": "earnings",
    "case_shop_2022q2_earnings": "earnings",
    "case_hindenburg_nikola_2020": "short_report",
    "case_gme_2021_01_squeeze": "short_report",
    "case_luckin_2020_fraud": "short_report",
    "case_fomc_2022_75bp": "macro",
    "case_cpi_2022_06_hot": "macro",
    "S1_short_report_cascade": "short_report",
    "S2_short_report_regulatory_overhang": "short_report",
    "M3_meme_attention_liquidity": "short_report",
    "X1_fomc_rate_shock": "macro",
    "X2_cpi_rotation_beta": "macro",
    "M4_fed_macro_shock": "macro",
}

SCENARIO_MVP = SCENARIO_DOMAIN

WORLD_IDS = ["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7"]

WORLD_DESCRIPTIONS = {
    "W0": "Baseline — no counterfactual intervention",
    "W1": "No analyst downgrade path",
    "W2": "No social/retail amplification",
    "W3": "Company timely clarification",
    "W4": "Higher market liquidity support",
    "W5": "No macro risk shock",
    "W6": "No options gamma amplification",
    "W7": "No sector spillover",
}

DEFAULT_RESOURCES = {
    "market_maker_capacity": 100,
    "borrow_availability": 80,
    "analyst_coverage_channel": 10,
    "corporate_comm_channel": 5,
    "circuit_breaker_buffer": 3,
    "options_dealer_hedging_capacity": 50,
}


def default_state() -> dict[str, float]:
    return {key: 0.0 for key in STATE_KEYS}


def default_state_with_baseline() -> dict[str, float]:
    state = default_state()
    state["fundamental_expectation"] = 0.55
    state["investor_sentiment"] = 0.5
    state["liquidity_depth"] = 0.6
    state["macro_risk_appetite"] = 0.5
    state["volatility_state"] = 0.3
    state["trust_level"] = 0.55
    state["stock_beta_exposure"] = 0.5
    return state
