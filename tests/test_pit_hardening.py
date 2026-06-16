"""Tests for Step C PIT data hardening."""

from __future__ import annotations

from market_causal_engine.case_study import run_case_study
from market_causal_engine.evidence import MarketAtom
from market_causal_engine.lookahead import LookAheadPolicy
from market_causal_engine.platform.pit import SourceKind
from market_causal_engine.platform.pit_hardening import (
    CaseTimeAxis,
    atom_to_pit_record,
    audit_atom_pit,
    audit_case_study,
    build_atom_temporal,
    enrich_atom_temporal,
    summarize_pit_compliance,
)


def test_case_time_axis_minute_to_iso():
    axis = CaseTimeAxis(origin_iso="2022-04-19T16:01:00-04:00", event_date="2022-04-19")
    iso0 = axis.minute_to_iso(0)
    iso15 = axis.minute_to_iso(15)
    assert iso0 != iso15
    assert "+00:00" in iso0 or iso0.endswith("Z")


def test_build_atom_temporal_ordering():
    axis = CaseTimeAxis(origin_iso="2022-04-19T16:01:00-04:00")
    atom = MarketAtom(
        atom_id="A1",
        text="test",
        source="8-K",
        time=0,
        published_at=15,
        metadata={"source_class": "primary_filing"},
    )
    temporal = build_atom_temporal(atom, axis)
    assert temporal["observed_time"] <= temporal["published_time"]
    assert temporal["published_time"] <= temporal["ingested_time"]


def test_enrich_atom_temporal_idempotent():
    axis = CaseTimeAxis(origin_iso="2022-04-19T16:01:00-04:00")
    atom = MarketAtom("A1", "t", "8-K", 0, published_at=0, metadata={})
    e1 = enrich_atom_temporal(atom, axis)
    e2 = enrich_atom_temporal(e1, axis)
    assert e1.metadata["temporal"] == e2.metadata["temporal"]


def test_atom_to_pit_record_admissible():
    axis = CaseTimeAxis(origin_iso="2022-04-19T16:01:00-04:00")
    atom = MarketAtom("A1", "t", "8-K", 0, published_at=0, metadata={"source_class": "primary_filing"})
    rec = atom_to_pit_record(atom, axis=axis, ticker="NFLX")
    assert rec.source_kind == SourceKind.SEC_EDGAR
    assert rec.admissible_at(axis.as_of_iso(120))


def test_audit_rejects_lookahead_trap():
    axis = CaseTimeAxis(origin_iso="2022-04-19T16:01:00-04:00")
    trap = MarketAtom(
        atom_id="TRAP",
        text="post-mortem calibration label",
        source="research",
        time=60,
        published_at=60,
        metadata={"source_class": "calibration_label", "uses_future_price": True},
    )
    violations = audit_atom_pit(trap, axis=axis, as_of_minutes=120, policy=LookAheadPolicy())
    codes = {v.code for v in violations}
    assert codes & {"forbidden_post_hoc_source", "future_price_leak"}


def test_nflx_case_study_pit_audit_passes():
    result = run_case_study("nflx_2022q1_earnings", as_of=120)
    pit = result.get("pit_audit")
    assert pit is not None
    assert pit["passed"] is True
    assert pit["envelope_coverage"] == 1.0
    assert pit.get("violations_by_code", {}).get("published_after_ingested", 0) == 0
    assert result["case_study"]["pit_audit_passed"] is True


def test_audit_case_study_helper():
    report = audit_case_study("nflx_2022q1_earnings", as_of_minutes=120)
    assert report["case_id"] == "nflx_2022q1_earnings"
    assert report["passed"] is True


def test_summarize_pit_compliance():
    summary = summarize_pit_compliance(
        [{"passed": True, "envelope_coverage": 1.0}, {"passed": True, "envelope_coverage": 0.9}]
    )
    assert summary["all_passed"] is True
    assert summary["n"] == 2
