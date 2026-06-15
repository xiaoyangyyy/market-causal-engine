"""Tests for SEC parser coverage and 6-K earnings fetch."""

from __future__ import annotations

import json
from unittest.mock import patch

from market_causal_engine.extraction.edgar_fetch import (
    EdgarFiling,
    EARNINGS_FILING_FORMS,
    _score_attachment,
    fetch_earnings_attachments,
    fetch_edgar_8k_package,
    find_filings,
)
from market_causal_engine.extraction.sec_parser import parse_sec_document, parse_sec_heuristic


SHAREHOLDER_LETTER = (
    "Netflix, Inc. today announced financial results for its first quarter ended March 31, 2022. "
    "Total revenue grew 9.8 percent year over year to $7.87 billion. "
    "The company reported a net loss of 200,000 paid memberships in Q1 versus consensus expectations "
    "for a gain of approximately 2.5 million subscribers. "
    "Diluted EPS was $3.20, missing Wall Street expectations near $3.68. "
    "Netflix expects Q2 revenue growth to slow and projects a loss of 2 million subscribers."
)

FINANCIALS_SNIPPET = (
    "Shopify Inc. announced financial results for the quarter ended September 30, 2017. "
    "Total revenue was $171.5 million, an increase of 72% over the same period in 2016. "
    "The company expects fourth quarter revenue growth to remain strong."
)


def test_parse_sec_document_patterns_and_heuristic():
    atoms, _ = parse_sec_document(
        SHAREHOLDER_LETTER,
        doc_id="test",
        source_type="sec_8k",
        published_offset_min=0,
        case_prefix="TST",
        heuristic_fallback=True,
    )
    assert len(atoms) >= 3
    assert any(a.metadata.get("extracted_by") == "earnings_release" for a in atoms)


def test_parse_sec_heuristic_foreign_financials():
    atoms, _ = parse_sec_heuristic(
        FINANCIALS_SNIPPET,
        source_type="sec_6k",
        published_offset_min=0,
        case_prefix="SHOP",
    )
    assert len(atoms) >= 1
    assert atoms[0].source == "6-K"
    assert "revenue" in atoms[0].text.lower()


def test_score_attachment_prefers_financials_over_certification():
    assert _score_attachment("financials-q32017.htm", "") > _score_attachment(
        "exhibit993q3201752-109f2ceo.htm", "CERTIFICATION"
    )
    assert _score_attachment("exhibit993q3201752-109f2ceo.htm", "CERTIFICATION") < 0


def test_find_filings_includes_6k():
    payload = {
        "filings": {
            "recent": {
                "form": ["6-K", "10-Q"],
                "filingDate": ["2017-10-31", "2017-11-01"],
                "accessionNumber": ["0001594806-17-000048", "0001594806-17-000099"],
                "primaryDocument": ["shop6kq32017.htm", "shop10q.htm"],
            }
        }
    }
    with patch(
        "market_causal_engine.extraction.edgar_fetch._http_get",
        return_value=json.dumps(payload).encode("utf-8"),
    ):
        hits = find_filings(
            "0001594806",
            forms=EARNINGS_FILING_FORMS,
            event_date="2017-10-31",
            date_from="2017-10-01",
            date_to="2017-11-30",
        )
    assert len(hits) == 1
    assert hits[0].form == "6-K"


def test_fetch_earnings_attachments_merges_financials():
    filing = EdgarFiling(
        form="6-K",
        filing_date="2017-10-31",
        accession_number="0001594806-17-000048",
        primary_document="shop6kq32017.htm",
        cik="0001594806",
    )
    index = {
        "directory": {
            "item": [
                {"name": "shop6kq32017.htm", "description": "6-K"},
                {"name": "financials-q32017.htm", "description": "Financial statements"},
                {"name": "mda-q32017.htm", "description": "MD&A"},
            ]
        }
    }

    with patch(
        "market_causal_engine.extraction.edgar_fetch.fetch_filing_index",
        return_value=index["directory"]["item"],
    ), patch(
        "market_causal_engine.extraction.edgar_fetch.fetch_attachment_text",
        side_effect=lambda _f, name: (
            FINANCIALS_SNIPPET
            if "financial" in name
            else "Management's discussion and analysis of financial condition and results of operations: "
            "revenue outlook remains stable with continued merchant growth across North America and international regions."
        ),
    ):
        merged = fetch_earnings_attachments(filing)

    assert "revenue was" in merged.lower()
    assert "merchant growth" in merged.lower()


def test_fetch_edgar_8k_package_searches_6k_when_configured():
    filing = EdgarFiling(
        form="6-K",
        filing_date="2017-10-31",
        accession_number="0001594806-17-000048",
        primary_document="shop6kq32017.htm",
        cik="0001594806",
    )
    with patch(
        "market_causal_engine.extraction.edgar_fetch.resolve_cik",
        return_value="0001594806",
    ), patch(
        "market_causal_engine.extraction.edgar_fetch.find_filings",
        return_value=[filing],
    ) as mock_find, patch(
        "market_causal_engine.extraction.edgar_fetch.fetch_filing_text",
        return_value="FORM 6-K foreign issuer report",
    ), patch(
        "market_causal_engine.extraction.edgar_fetch.fetch_earnings_attachments",
        return_value=FINANCIALS_SNIPPET,
    ):
        text, picked = fetch_edgar_8k_package(
            "SHOP",
            "2017-10-31",
            date_from="2017-10-01",
            date_to="2017-11-30",
        )

    mock_find.assert_called_once()
    assert mock_find.call_args.kwargs["forms"] == EARNINGS_FILING_FORMS
    assert picked.form == "6-K"
    assert "revenue was" in text.lower()
