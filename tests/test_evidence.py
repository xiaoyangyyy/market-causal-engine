"""Evidence layer unit tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from worldcup_causal_engine.evidence import Atom, EvidenceLedger, cluster_key, time_bucket


def _atom(i: int, **kwargs) -> Atom:
    defaults = {
        "source_id": f"src_{i}",
        "time": 25,
        "claim_type": "blame_referee",
        "target": "referee",
        "actor_group": "Team_A_fans",
        "emotion": "anger",
        "confidence": 0.8,
        "raw_text": f"text_{i}",
    }
    defaults.update(kwargs)
    return Atom(**defaults)


def test_time_bucket():
    assert time_bucket(25) == "t20_30"
    assert time_bucket(70) == "t70_80"


def test_hundred_atoms_one_cluster():
    ledger = EvidenceLedger(match_id="M12")
    for i in range(100):
        ledger.ingest(_atom(i, source_id=f"src_{i % 30}"))
    assert len(ledger.clusters) == 1
    cluster = next(iter(ledger.clusters.values()))
    assert cluster.support_count == 100
    assert cluster.unique_sources == 30


def test_dedup_same_source_text():
    ledger = EvidenceLedger()
    a1 = _atom(1, source_id="s1", raw_text="same text")
    a2 = _atom(2, source_id="s1", raw_text="same text")
    ledger.ingest(a1)
    cid = ledger.ingest(a2)
    cluster = next(iter(ledger.clusters.values()))
    assert cluster.support_count == 1
    assert cid is None


def test_low_confidence_stored_not_clustered():
    ledger = EvidenceLedger(min_confidence=0.3)
    ledger.ingest(_atom(1, confidence=0.1))
    assert len(ledger.atoms) == 1
    assert len(ledger.clusters) == 0


def test_contestation_defend_referee():
    ledger = EvidenceLedger()
    for i in range(60):
        ledger.ingest(_atom(i, claim_type="blame_referee", source_id=f"b_{i}"))
    blame = next(iter(ledger.clusters.values()))
    before = blame.contestation
    for i in range(10):
        ledger.ingest(_atom(100 + i, claim_type="defend_referee", actor_group="Team_B_fans", source_id=f"d_{i}"))
    assert blame.contestation > before


def test_ledger_save_load():
    ledger = EvidenceLedger(ledger_id="test_ledger")
    for i in range(5):
        ledger.ingest(_atom(i))
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        path = tmp.name
    ledger.save(path)
    loaded = EvidenceLedger.load(path)
    assert loaded.ledger_id == "test_ledger"
    assert len(loaded.atoms) == 5
    assert len(loaded.clusters) == 1


def test_cluster_key_format():
    atom = _atom(1, time=72)
    key = cluster_key(atom, "M12")
    assert key.startswith("blame_referee|Team_A_fans|referee|M12|t70_80")
