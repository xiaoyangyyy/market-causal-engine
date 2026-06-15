"""Market price, volume, sector ETF, and options IV stub ingestion."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_causal_engine.extraction.edgar_fetch import _user_agent
from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.pit import PITRecord, SourceKind, TemporalEnvelope
from market_causal_engine.platform.watchlist import load_watchlist, sector_etf_for

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _yahoo_chart(symbol: str, *, interval: str = "1d", range_: str = "1mo") -> dict[str, Any]:
    url = YAHOO_CHART.format(symbol=symbol) + f"?interval={interval}&range={range_}"
    req = Request(url, headers={"User-Agent": _user_agent()})
    with urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_bars(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return []
    meta = result[0].get("meta", {})
    timestamps = result[0].get("timestamp") or []
    indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
    closes = indicators.get("close") or []
    volumes = indicators.get("volume") or []
    bars: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()
        bars.append(
            {
                "time": dt,
                "close": float(closes[i]),
                "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                "currency": meta.get("currency", "USD"),
            }
        )
    return bars


def _options_iv_stub(symbol: str) -> dict[str, Any]:
    """Placeholder IV surface — full chain in P2 via vendor API."""
    return {
        "iv_30d": None,
        "put_call_ratio": None,
        "stub": True,
        "note": "Options IV stub; wire Polygon/CBOE in P2",
        "symbol": symbol,
    }


class MarketPricesIngestor(Ingestor):
    """Fetch daily + intraday bars and sector ETF context via Yahoo chart API."""

    source_kind = SourceKind.MARKET_PRICE

    def __init__(self, *, watchlist: dict[str, Any] | None = None) -> None:
        self.watchlist = watchlist or load_watchlist()

    def ingest(self, ctx: IngestContext) -> IngestResult:
        t0 = time.monotonic()
        result = IngestResult(source_kind=self.source_kind)
        tickers = ctx.tickers or list(self.watchlist.get("tickers", []))

        for ticker in tickers[:10]:
            sym = ticker.upper()
            etf = sector_etf_for(sym, self.watchlist)
            try:
                daily = _parse_bars(_yahoo_chart(sym, interval="1d", range_="1mo"))
                intraday = _parse_bars(_yahoo_chart(sym, interval="1h", range_="5d"))
                etf_daily = _parse_bars(_yahoo_chart(etf, interval="1d", range_="1mo"))
                result.fetched += len(daily) + len(intraday) + len(etf_daily)

                if not daily:
                    result.errors.append(f"{sym}: no daily bars")
                    continue

                last_bar = daily[-1]
                published = last_bar["time"]
                if published > ctx.as_of_time:
                    result.skipped += 1
                    continue

                iv_stub = _options_iv_stub(sym)
                record = PITRecord(
                    record_id=f"mkt_{uuid.uuid4().hex[:12]}",
                    source_kind=SourceKind.MARKET_PRICE,
                    source_id=f"market:{sym}:daily",
                    payload={
                        "ticker": sym,
                        "sector_etf": etf,
                        "daily_bars": daily[-5:],
                        "intraday_bars": intraday[-8:],
                        "sector_etf_bars": etf_daily[-5:],
                        "last_close": last_bar["close"],
                        "last_volume": last_bar.get("volume"),
                        "options_iv": iv_stub,
                    },
                    temporal=TemporalEnvelope(
                        observed_time=published,
                        published_time=published,
                        ingested_time=_utc_now_iso(),
                        revision_id=f"daily:{published[:10]}",
                    ),
                    metadata={"run_id": ctx.run_id},
                )
                result.records.append(record)
                result.stored += 1

                if etf_daily:
                    etf_bar = etf_daily[-1]
                    etf_pub = etf_bar["time"]
                    if etf_pub <= ctx.as_of_time:
                        result.records.append(
                            PITRecord(
                                record_id=f"mkt_{uuid.uuid4().hex[:12]}",
                                source_kind=SourceKind.MARKET_PRICE,
                                source_id=f"market:{etf}:sector",
                                payload={
                                    "ticker": sym,
                                    "sector_etf": etf,
                                    "last_close": etf_bar["close"],
                                    "bars": etf_daily[-3:],
                                },
                                temporal=TemporalEnvelope(
                                    observed_time=etf_pub,
                                    published_time=etf_pub,
                                    ingested_time=_utc_now_iso(),
                                    revision_id=f"sector:{etf_pub[:10]}",
                                ),
                                metadata={"run_id": ctx.run_id, "role": "sector_etf"},
                            )
                        )
                        result.stored += 1
            except (HTTPError, URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
                result.errors.append(f"{sym}: {exc}")

        result.duration_ms = (time.monotonic() - t0) * 1000
        return result
