"""Tests for SEC EDGAR fetch helper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from market_causal_engine.extraction.edgar_fetch import (
    EdgarFiling,
    fetch_edgar_for_case,
    find_filings,
    html_to_text,
    list_edgar_fetchable_cases,
    resolve_cik,
)

ROOT = Path(__file__).resolve().parent.parent


def test_html_to_text_strips_tags():
    html = "<html><body><p>Revenue miss</p><div>Guidance cut</div></body></html>"
    text = html_to_text(html)
    assert "Revenue miss" in text
    assert "Guidance cut" in text


def test_list_edgar_fetchable_cases():
    cases = list_edgar_fetchable_cases()
    assert "nflx_2022q1_earnings" in cases
    assert "shop_2022q2_earnings" in cases


def test_resolve_cik_from_cache(tmp_path, monkeypatch):
    cache = tmp_path / "company_tickers.json"
    cache.write_text(
        json.dumps({"0": {"cik_str": 106528, "ticker": "NFLX"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("market_causal_engine.extraction.edgar_fetch._cache_path", lambda name: cache)

    with patch("market_causal_engine.extraction.edgar_fetch._http_get") as mock_get:
        assert resolve_cik("NFLX") == "0000106528"
        mock_get.assert_not_called()


def test_find_filings_filters_by_date():
    cik = "0000106528"
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q"],
                "filingDate": ["2022-04-19", "2022-04-01"],
                "accessionNumber": ["0001065280-22-000123", "0001065280-22-000001"],
                "primaryDocument": ["nflx-20220419.htm", "nflx-10q.htm"],
            }
        }
    }
    with patch(
        "market_causal_engine.extraction.edgar_fetch._http_get",
        return_value=json.dumps(payload).encode("utf-8"),
    ):
        hits = find_filings(cik, event_date="2022-04-19", window_days=1)
    assert len(hits) == 1
    assert hits[0].form == "8-K"


def test_fetch_edgar_for_case_writes_edgar_file(tmp_path, monkeypatch):
    case_id = "shop_2022q2_earnings"
    case_root = ROOT / "data" / "market" / "case_studies" / case_id
    out = case_root / "sources" / "sec_8k_edgar.txt"
    if out.exists():
        out.unlink()

    filing = EdgarFiling(
        form="8-K",
        filing_date="2022-07-26",
        accession_number="0001594806-22-000001",
        primary_document="shop-8k.htm",
        cik="0001594806",
    )

    with patch("market_causal_engine.extraction.edgar_fetch.resolve_cik", return_value="0001594806"), patch(
        "market_causal_engine.extraction.edgar_fetch.find_filings",
        return_value=[filing],
    ), patch(
        "market_causal_engine.extraction.edgar_fetch.fetch_filing_text",
        return_value="Shopify reports Q2 revenue miss and lowers guidance.",
    ):
        report = fetch_edgar_for_case(case_id)

    assert report["case_id"] == case_id
    assert out.exists()
    assert "revenue miss" in out.read_text(encoding="utf-8").lower()
