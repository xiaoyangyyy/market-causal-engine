"""Load platform watchlist configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from market_causal_engine.platform.storage.factory import default_watchlist_path


def load_watchlist(path: Path | None = None) -> dict[str, Any]:
    p = path or default_watchlist_path()
    if not p.exists():
        return {"tickers": [], "sector_etfs": {}, "edgar_forms": ["8-K"], "poll_lookback_days": 30}
    return json.loads(p.read_text(encoding="utf-8"))


def sector_etf_for(ticker: str, watchlist: dict[str, Any] | None = None) -> str:
    wl = watchlist or load_watchlist()
    mapping = wl.get("sector_etfs", {})
    return str(mapping.get(ticker.upper(), mapping.get("DEFAULT", "SPY")))
