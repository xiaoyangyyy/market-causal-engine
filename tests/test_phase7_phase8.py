"""Phase 7 (MDG + typed evidence) and Phase 8 (calibration) tests.

Phase 8 tests are added after calibration MVP is implemented.
"""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.mdg.builder import build_event_mdg_from_result
from worldcup_causal_engine.scenarios import run_scenario
from worldcup_causal_engine.evidence import Atom
from worldcup_causal_engine.calibration.observations import Dataset
from worldcup_causal_engine.calibration.search import random_search
from worldcup_causal_engine.scenarios import load_priors

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"
S3 = ROOT / "data" / "scenarios" / "S3_heat_crowd_comm_delay.json"


def test_mdg_contains_trace_successor_edges_s1():
    result = run_scenario(S1, world_id="W0", until=120)
    mdg = build_event_mdg_from_result(result)
    path = result["dominant_path"]
    assert len(path) >= 3
    # adjacency edges should exist at least for the dominant path.
    for a, b in zip(path, path[1:]):
        edge = mdg.edges.get((a, b))
        assert edge is not None
        assert any(ev.edge_type in ("trace_successor", "spec_emits", "contract_emits") for ev in edge.evidences)


def test_atom_evidence_type_default_mapping():
    a = Atom(
        source_id="x",
        time=1,
        claim_type="blame_referee",
        target="referee",
        actor_group="fans",
        emotion="anger",
        confidence=0.7,
        raw_text="text",
    )
    assert a.evidence_type == "online_rumor"


def test_calibration_random_search_runs(tmp_path):
    obs_path = ROOT / "data" / "observations" / "synthetic_s1_w0_final.jsonl"
    dataset = Dataset.load_jsonl(obs_path)
    base_priors = load_priors()

    res = random_search(
        scenario_path=str(S1),
        world_id="W0",
        dataset=dataset,
        base_priors=base_priors,
        param_space={"rumor_amplified": {"rumor_delta": (0.4, 1.0)}},
        budget=10,
        seed=1,
        until=120,
    )
    assert res.tried == 10
    assert res.best_loss >= 0.0


def test_calibrated_priors_improves_s3_panic_vs_v01():
    from worldcup_causal_engine.calibration.merge_priors import write_calibrated_priors
    from worldcup_causal_engine.calibration.objective import evaluate_loss
    from worldcup_causal_engine.calibration.observations import Dataset

    write_calibrated_priors()
    obs = Dataset.load_jsonl(ROOT / "data" / "observations" / "real_qatar2022_S3_w0.jsonl")

    v01 = run_scenario(S3, world_id="W0", priors_profile="v0.1")
    cal_global = run_scenario(S3, world_id="W0", priors_profile="calibrated")
    cal_specific = run_scenario(
        S3, world_id="W0", priors_profile="calibrated", scenario_specific_priors=True
    )

    assert evaluate_loss(v01, obs).total > evaluate_loss(cal_global, obs).total
    assert cal_specific["final_risk"]["panic"] < v01["final_risk"]["panic"]
    assert cal_specific["priors_profile"] == "calibrated"


def test_s1_calibrated_verbal_near_qatar_observation():
    from worldcup_causal_engine.calibration.objective import evaluate_loss

    obs = Dataset.load_jsonl(ROOT / "data" / "observations" / "real_qatar2022_S1_w0.jsonl")
    target = next(o.value for o in obs.observations if o.key == "verbal_conflict")

    r = run_scenario(
        S1,
        world_id="W0",
        priors_profile="calibrated",
        scenario_specific_priors=True,
    )
    verbal = r["final_risk"]["verbal_conflict"]
    assert abs(verbal - target) < 0.03
    assert evaluate_loss(r, obs).total < 0.01


def test_real_world_observation_builder():
    from worldcup_causal_engine.calibration.normalize_realworld import (
        build_observations_for_scenario,
    )

    records = build_observations_for_scenario("S1", raw_dir=ROOT / "data" / "calibration_raw")
    assert records
    keys = {r["key"] for r in records}
    assert "verbal_conflict" in keys
    assert "rumor_volume_index" in keys
    assert all(r["meta"]["url"].startswith("http") for r in records)


def test_normalize_to_observations_jsonl(tmp_path):
    from worldcup_causal_engine.calibration.downloaders.normalize import (
        normalize_to_observations_jsonl,
    )

    out = tmp_path / "obs.jsonl"
    path = normalize_to_observations_jsonl(
        [
            {
                "scenario_id": "S1_controversial_call_high_density",
                "world_id": "W0",
                "time_bucket": "final",
                "key": "verbal_conflict",
                "value": 0.1,
                "weight": 1.0,
            }
        ],
        out_path=out,
    )
    assert Path(path).exists()

