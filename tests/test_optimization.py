"""Tests for feed event coalescing, EDGAR summary merge, and macro fetch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from market_causal_engine.evidence import MarketAtom
from market_causal_engine.extraction.edgar_preprocess import preprocess_edgar_filing
from market_causal_engine.extraction.macro_fetch import fetch_macro_for_case, list_macro_fetchable_cases
from market_causal_engine.extraction.pipeline import extract_from_case
from market_causal_engine.feed import FeedRunner
from market_causal_engine.kernel import Kernel

ROOT = Path(__file__).resolve().parent.parent


def test_edgar_preprocess_extracts_item_202():
    raw = """
    <html><body>
    Item 2.02 Results of Operations and Financial Condition
    On April 19, 2022 Netflix reported Q1 revenue and a subscriber loss of 200k versus expectations.
    The company lowers Q2 revenue outlook due to slower member growth.
    </body></html>
    """
    out = preprocess_edgar_filing(raw)
    assert "subscriber loss" in out.lower()
    assert "lowers" in out.lower()


def test_feed_coalesces_duplicate_event_kind_at_same_time():
    kernel = Kernel()
    runner = FeedRunner(kernel, skip_evidence_ledger=True, as_of=120)
    atoms = [
        MarketAtom(
            atom_id="A1",
            text="Netflix reports Q1 revenue miss on subscriber loss",
            source="8-K",
            time=0,
            published_at=0,
            tags=["earnings"],
            metadata={"severity": 0.8, "miss_severity": 0.85},
        ),
        MarketAtom(
            atom_id="A2",
            text="Netflix reports Q1 EPS miss versus consensus",
            source="8-K",
            time=0,
            published_at=0,
            tags=["earnings"],
            metadata={"severity": 0.9, "miss_severity": 0.9},
        ),
    ]
    runner.run_atoms(atoms, until=30)
    kinds = [e.kind for e in kernel.trace if e.action == "executed" and e.kind == "earnings_release"]
    assert len(kinds) == 1


def test_feed_single_shots_ad_revenue_path():
    kernel = Kernel()
    runner = FeedRunner(kernel, skip_evidence_ledger=True, as_of=120)
    atoms = [
        MarketAtom(
            atom_id="S1",
            text="Snap reports Q3 ad revenue miss and digital ad market worsened",
            source="8-K",
            time=0,
            published_at=0,
            tags=["ad_revenue", "earnings"],
            metadata={"severity": 0.88},
        ),
        MarketAtom(
            atom_id="S2",
            text="advertisers cutting budgets due to macro uncertainty",
            source="transcript",
            time=45,
            published_at=45,
            tags=["ad_revenue", "earnings"],
            metadata={"severity": 0.85},
        ),
    ]
    runner.run_atoms(atoms, until=60)
    ingested = [e.kind for e in kernel.trace if e.action == "executed" and e.kind == "ad_revenue_miss"]
    assert len(ingested) == 1


def test_pipeline_prefers_edgar_summary_for_shop():
    case_id = "shop_2022q2_earnings"
    summary = ROOT / "data" / "market" / "case_studies" / case_id / "sources" / "sec_8k_edgar_summary.txt"
    if not summary.exists():
        return
    _, report = extract_from_case(case_id)
    sec_doc = next(d for d in report["documents"] if d["doc"] == "sec_8k.txt")
    assert "edgar_summary" in sec_doc["status"]


def test_list_macro_fetchable_cases():
    cases = list_macro_fetchable_cases()
    assert "fomc_2022_75bp" in cases
    assert "cpi_2022_06_hot" in cases


def test_fetch_macro_for_case_writes_file():
    case_id = "fomc_2022_75bp"
    case_root = ROOT / "data" / "market" / "case_studies" / case_id
    out = case_root / "sources" / "fomc_statement_fetched_test.txt"
    if out.exists():
        out.unlink()

    sources = json.loads((case_root / "sources" / "sources.json").read_text(encoding="utf-8"))
    cfg = dict(sources["macro_fetch"])
    cfg["output"] = "fomc_statement_fetched_test.txt"

    with patch(
        "market_causal_engine.extraction.macro_fetch.load_sources_manifest",
        return_value={**sources, "macro_fetch": cfg},
    ), patch(
        "market_causal_engine.extraction.macro_fetch.fetch_fomc_statement",
        return_value="The FOMC decided to raise the interest rate by 75 basis points.",
    ):
        report = fetch_macro_for_case(case_id)

    assert report["case_id"] == case_id
    assert out.exists()
    out.unlink()
