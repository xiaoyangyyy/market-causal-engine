"""Quick summary of case study effectiveness."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_causal_engine.case_study import run_case_counterfactual, run_case_study


def summarize(case_id: str, as_of: int) -> None:
    r = run_case_study(case_id, as_of=as_of)
    cs = r["case_study"]
    cal = r.get("calibrated_impact", {})
    contrib = r.get("mechanism_contributions", {})
    print(f"\n=== {case_id} (as_of={as_of}min) ===")
    print(f"Direction match: {cs.get('direction_match')}")
    sim = cs.get("simulated_outcomes", {})
    obs = cs.get("observed_outcomes", {})
    print(f"Observed AH: {obs.get('after_hours_return_pct')}%")
    print(f"Sim drawdown: {sim.get('drawdown_risk')} | pressure: {sim.get('directional_pressure')}")
    print(f"Calibrated AH est: {cal.get('estimated_after_hours_return_pct')}% (error {cal.get('after_hours_error_pct')}%)")
    print(f"Path: {' -> '.join(r.get('dominant_causal_path', [])[:6])}")
    print(f"Contributions: fundamental={contrib.get('fundamental',0):.2f} sentiment={contrib.get('sentiment',0):.2f} liquidity={contrib.get('liquidity',0):.2f}")
    print(f"Look-ahead: {r['lookahead_audit']['accepted_count']} ok, {r['lookahead_audit']['rejected_count']} rejected")


def counterfactual(case_id: str, as_of: int) -> None:
    suite = run_case_counterfactual(case_id, until=as_of)
    print(f"\n=== Counterfactual {case_id} ===")
    for wid in ["W0", "W1", "W3", "W6"]:
        sim = suite["runs"][wid]["simulated_outcomes"]
        cal = suite["runs"][wid].get("calibrated_impact", {})
        print(f"  {wid}: drawdown={sim.get('drawdown_risk')} est_AH={cal.get('estimated_after_hours_return_pct')}%")


if __name__ == "__main__":
    summarize("nflx_2022q1_earnings", 120)
    summarize("snap_2022q3_earnings", 100)
    counterfactual("nflx_2022q1_earnings", 120)
