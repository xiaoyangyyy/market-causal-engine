"""Control ticker selection for counterfactual estimation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "market" / "counterfactuals" / "peer_config.json"


def load_peer_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {"sector_etf": {}, "peer_overrides": {}, "defaults": {"market": ["SPY"], "growth": ["QQQ"]}}
    return json.loads(path.read_text(encoding="utf-8"))


def sector_etf_for(ticker: str, config: dict[str, Any] | None = None) -> str | None:
    cfg = config or load_peer_config()
    return cfg.get("sector_etf", {}).get(ticker.upper())


def select_controls(
    ticker: str,
    *,
    config: dict[str, Any] | None = None,
    max_peers: int = 4,
) -> list[str]:
    """
    Build control basket: sector peers + sector ETF + SPY + QQQ (deduped, treated excluded).
    """
    cfg = config or load_peer_config()
    treated = ticker.upper()
    controls: list[str] = []

    peers = list(cfg.get("peer_overrides", {}).get(treated, []))
    etf = sector_etf_for(treated, cfg)
    if etf:
        controls.append(etf.upper())
    controls.extend(p.upper() for p in peers[:max_peers])
    defaults = cfg.get("defaults", {})
    controls.extend(defaults.get("market", ["SPY"]))
    controls.extend(defaults.get("growth", ["QQQ"]))

    out: list[str] = []
    seen: set[str] = set()
    for sym in controls:
        sym = sym.upper()
        if sym == treated or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out
