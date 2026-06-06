"""Atom extraction pipeline: SEC filings and news -> JSONL evidence."""

from market_causal_engine.extraction.edgar_fetch import fetch_edgar_for_case, list_edgar_fetchable_cases
from market_causal_engine.extraction.macro_fetch import fetch_macro_for_case, list_macro_fetchable_cases
from market_causal_engine.extraction.pipeline import build_atoms_for_case, extract_from_case

__all__ = [
    "build_atoms_for_case",
    "extract_from_case",
    "fetch_edgar_for_case",
    "fetch_macro_for_case",
    "list_edgar_fetchable_cases",
    "list_macro_fetchable_cases",
]