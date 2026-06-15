"""Default production ingestors for P1 data layer."""

from __future__ import annotations

from market_causal_engine.platform.ingestion.base import Ingestor
from market_causal_engine.platform.ingestion.edgar_poll import EdgarPollIngestor
from market_causal_engine.platform.ingestion.fred_bls import FredBlsIngestor
from market_causal_engine.platform.ingestion.market_prices import MarketPricesIngestor
from market_causal_engine.platform.ingestion.news_merge import NewsMergedIngestor
from market_causal_engine.platform.storage.base import PlatformStore


def default_ingestors(store: PlatformStore | None = None) -> list[Ingestor]:
    return [
        NewsMergedIngestor(),
        FredBlsIngestor(store=store),
        EdgarPollIngestor(store=store),
        MarketPricesIngestor(),
    ]
