"""Compiler unit and integration tests."""

from __future__ import annotations

from pathlib import Path

from worldcup_causal_engine.compiler import Compiler, compile_cluster, load_default_rules, should_compile
from worldcup_causal_engine.evidence import Atom, ClaimCluster, EvidenceLedger
from worldcup_causal_engine.feed import FeedRunner
from worldcup_causal_engine.reverse import analyze_result
from worldcup_causal_engine.scenarios import run_scenario

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "data" / "scenarios" / "S1_controversial_call_high_density.json"
FEED = ROOT / "data" / "atoms" / "sample_match_feed.jsonl"
RULES = ROOT / "data" / "compiler_rules" / "v0.1.json"


def _make_cluster(**kwargs) -> ClaimCluster:
    defaults = {
        "cluster_id": "C1",
        "key": "k",
        "claim_type": "blame_referee",
        "target": "referee",
        "actor_group": "Team_A_fans",
        "time_bucket": "t70_80",
        "support_count": 60,
        "unique_sources": 25,
        "velocity": 0.5,
        "emotion_intensity": 0.8,
        "confidence": 0.75,
        "contestation": 0.2,
    }
    defaults.update(kwargs)
    return ClaimCluster(**defaults)


def test_should_not_compile_below_threshold():
    rules = load_default_rules()
    rule = rules.get("blame_referee")
    cluster = _make_cluster(support_count=10, unique_sources=5, velocity=0.1)
    assert rule is not None
    assert should_compile(cluster, rule) is False


def test_should_compile_at_threshold():
    rules = load_default_rules()
    rule = rules.get("blame_referee")
    cluster = _make_cluster()
    assert rule is not None
    assert should_compile(cluster, rule) is True


def test_compile_produces_correct_event():
    rules = load_default_rules()
    rule = rules.get("blame_referee")
    cluster = _make_cluster()
    assert rule is not None
    event = compile_cluster(cluster, rule)
    assert event.kind == "media_blame_frame"
    assert event.cause == ["claim_cluster:C1"]
    assert event.payload["target"] == "referee"
    assert "severity" in event.payload


def test_cluster_compiled_once():
    ledger = EvidenceLedger()
    rules = load_default_rules()
    compiler = Compiler(rules)
    cluster = _make_cluster()
    ledger.clusters["C1"] = cluster

    first = compiler.try_compile(ledger)
    second = compiler.try_compile(ledger)

    assert len(first) == 1
    assert len(second) == 0
    assert "C1" in ledger.compiled_cluster_ids


def test_high_contestation_blocks_compile():
    rules = load_default_rules()
    rule = rules.get("blame_referee")
    cluster = _make_cluster(contestation=0.9)
    assert rule is not None
    assert should_compile(cluster, rule) is False


def test_s1_feed_end_to_end():
    if not FEED.exists():
        import subprocess
        subprocess.run(["python", str(ROOT / "scripts" / "generate_sample_feed.py")], check=True)

    result = run_scenario(S1, world_id="W0", until=120, feed_path=FEED)

    assert result.get("evidence_ledger")
    assert result["evidence_ledger"]["compiled_clusters"] >= 1
    assert result["evidence_ledger"]["total_atoms"] >= 200

    links = result.get("evidence_links", [])
    assert links
    assert any(l["event_kind"] == "media_blame_frame" for l in links)

    dbg = analyze_result(result)
    media_events = [
        e for e in result["trace"]
        if e["kind"] == "media_blame_frame" and e["action"] == "executed"
    ]
    feed_sourced = [
        e for e in media_events
        if any(c.startswith("claim_cluster:") for c in e.get("cause", []))
    ]
    assert feed_sourced

    executed = [e["kind"] for e in result["trace"] if e["action"] == "executed"]
    assert "controversial_call" in executed


def test_no_feed_regression():
    result = run_scenario(S1, world_id="W0", until=120)
    assert result["final_risk"]["verbal_conflict"] > 0.4
    assert "evidence_ledger" not in result
