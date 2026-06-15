"""Resumable backfill runner with progress tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from market_causal_engine.platform.ingestion.base import IngestContext
from market_causal_engine.platform.ingestion.edgar_poll import EdgarPollIngestor
from market_causal_engine.platform.ingestion.fred_bls import FredBlsIngestor
from market_causal_engine.platform.ingestion.market_prices import MarketPricesIngestor
from market_causal_engine.platform.provenance import new_run_id
from market_causal_engine.platform.registry import BackfillJob
from market_causal_engine.platform.storage.base import PlatformStore
from market_causal_engine.platform.storage.factory import get_platform_store
from market_causal_engine.platform.watchlist import load_watchlist


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


BACKFILL_HANDLERS: dict[str, str] = {
    "edgar_watchlist": "Poll EDGAR for all watchlist tickers",
    "macro_fred": "Backfill FRED series + macro case texts",
    "market_prices": "Backfill daily/intraday bars for watchlist",
    "all_sources": "Run all P1 ingestors sequentially",
}


class BackfillRunner:
    def __init__(self, store: PlatformStore | None = None) -> None:
        self.store = store or get_platform_store()

    def start(
        self,
        job_type: str,
        *,
        tickers: list[str] | None = None,
        batch_size: int = 1,
        resume_job_id: str | None = None,
    ) -> BackfillJob:
        if resume_job_id:
            job = self.store.get_job(resume_job_id)
            if not job:
                raise ValueError(f"Backfill job not found: {resume_job_id}")
            if job.status not in ("running", "pending", "failed"):
                raise ValueError(f"Job {resume_job_id} not resumable (status={job.status})")
            job.status = "running"
            job.error = None
            self.store.update_job(job)
            return self._execute(job)

        wl = load_watchlist()
        all_tickers = tickers or list(wl.get("tickers", []))
        job = BackfillJob(
            job_id=new_run_id("backfill"),
            job_type=job_type,
            status="running",
            cursor={"index": 0, "tickers": all_tickers},
            total=len(all_tickers) if job_type in ("edgar_watchlist", "market_prices") else 1,
            config={"batch_size": batch_size, "tickers": all_tickers},
        )
        self.store.create_job(job)
        return self._execute(job)

    def _execute(self, job: BackfillJob) -> BackfillJob:
        handler = {
            "edgar_watchlist": self._backfill_edgar,
            "macro_fred": self._backfill_macro,
            "market_prices": self._backfill_market,
            "all_sources": self._backfill_all,
        }.get(job.job_type)
        if not handler:
            job.status = "failed"
            job.error = f"Unknown job_type: {job.job_type}"
            self.store.update_job(job)
            return job
        try:
            handler(job)
            if job.status == "running":
                job.status = "succeeded"
            self.store.update_job(job)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
            self.store.update_job(job)
        return job

    def _ingest_ctx(self, job: BackfillJob, tickers: list[str]) -> IngestContext:
        return IngestContext(
            run_id=job.job_id,
            as_of_time=_utc_now_iso(),
            tickers=tickers,
            force_refresh=True,
        )

    def _backfill_edgar(self, job: BackfillJob) -> None:
        tickers: list[str] = list(job.config.get("tickers", []))
        idx = int(job.cursor.get("index", 0))
        batch = int(job.config.get("batch_size", 1))
        ingestor = EdgarPollIngestor(store=self.store)

        while idx < len(tickers):
            batch_tickers = tickers[idx : idx + batch]
            ctx = self._ingest_ctx(job, batch_tickers)
            result = ingestor.ingest(ctx)
            job.completed += result.stored
            if result.errors:
                job.failed += len(result.errors)
            idx += batch
            job.cursor = {"index": idx, "tickers": tickers}
            self.store.update_job(job)

        job.total = len(tickers)

    def _backfill_macro(self, job: BackfillJob) -> None:
        ingestor = FredBlsIngestor(store=self.store)
        ctx = self._ingest_ctx(job, [])
        result = ingestor.ingest(ctx)
        job.completed = result.stored
        job.failed = len(result.errors)
        job.total = 1
        job.cursor = {"done": True}

    def _backfill_market(self, job: BackfillJob) -> None:
        tickers: list[str] = list(job.config.get("tickers", []))
        idx = int(job.cursor.get("index", 0))
        batch = int(job.config.get("batch_size", 2))
        ingestor = MarketPricesIngestor()

        while idx < len(tickers):
            batch_tickers = tickers[idx : idx + batch]
            ctx = self._ingest_ctx(job, batch_tickers)
            result = ingestor.ingest(ctx)
            job.completed += result.stored
            if result.errors:
                job.failed += len(result.errors)
            idx += batch
            job.cursor = {"index": idx, "tickers": tickers}
            self.store.update_job(job)

        job.total = len(tickers)

    def _backfill_all(self, job: BackfillJob) -> None:
        steps: list[tuple[str, Callable[[BackfillJob], None]]] = [
            ("edgar", self._backfill_edgar),
            ("macro", self._backfill_macro),
            ("market", self._backfill_market),
        ]
        step_idx = int(job.cursor.get("step", 0))
        while step_idx < len(steps):
            name, fn = steps[step_idx]
            job.cursor = {"step": step_idx, "step_name": name, **job.cursor}
            self.store.update_job(job)
            fn(job)
            step_idx += 1
            job.cursor["step"] = step_idx
        job.cursor["done"] = True

    def status(self, job_id: str) -> BackfillJob | None:
        return self.store.get_job(job_id)

    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> list[BackfillJob]:
        return self.store.list_jobs(status=status, limit=limit)
