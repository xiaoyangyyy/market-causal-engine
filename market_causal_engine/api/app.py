"""FastAPI service for Event Intelligence / Causal Research Assistant."""

from __future__ import annotations

import logging
from typing import Any

from market_causal_engine.observability.logging import configure_logging
from market_causal_engine.observability.metrics import REGISTRY, Timer
from market_causal_engine.platform.backfill import BackfillRunner
from market_causal_engine.platform.pipeline import DailyPipeline
from market_causal_engine.platform.provenance import build_provenance, new_run_id
from market_causal_engine.platform.storage.factory import get_platform_store

logger = logging.getLogger("market_causal_engine.api")

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install api extras: pip install -e '.[api]'") from exc

configure_logging()

app = FastAPI(
    title="Market Event Causal Engine",
    description="Event Intelligence / Causal Research Assistant — not a trading signal service",
    version="0.5.0",
)

_storage = get_platform_store()
_pipeline = DailyPipeline(storage=_storage)
_backfill = BackfillRunner(_storage)


class IngestRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    force_refresh: bool = False
    offline: bool = False


class ReplayRequest(BaseModel):
    event_id: str
    as_of: int = 120
    world_id: str = "W0"


@app.get("/health")
def health() -> dict[str, Any]:
    freshness = _storage.freshness_report()
    status = "ok" if not freshness.get("stale") else "degraded"
    REGISTRY.set_gauge("data_freshness_ok", 1.0 if status == "ok" else 0.0)
    return {
        "status": status,
        "service": "market-causal-engine",
        "freshness": freshness,
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return REGISTRY.render_prometheus()


@app.post("/events/ingest")
def events_ingest(body: IngestRequest) -> dict[str, Any]:
    with Timer("ingest_duration_seconds"):
        run_id = new_run_id("ingest")
        result = _pipeline.run(
            run_id=run_id,
            tickers=body.tickers,
            skip_network_ingest=body.offline,
            replay_cases=False,
        )
        REGISTRY.inc("ingest_runs_total", labels={"status": result.status})
        if result.status != "succeeded":
            raise HTTPException(status_code=502, detail=result.error or "ingest failed")
        return result.to_dict()


@app.post("/events/replay")
def events_replay(body: ReplayRequest) -> dict[str, Any]:
    from market_causal_engine.case_study import run_case_study

    with Timer("replay_duration_seconds"):
        try:
            result = run_case_study(body.event_id, as_of=body.as_of, world_id=body.world_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            REGISTRY.inc("replay_errors_total")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    from market_causal_engine.case_study import load_case_manifest
    from market_causal_engine.counterfactuals.outcome_layer import attach_outcome_causal, build_event_card

    manifest = load_case_manifest(body.event_id)
    attach_outcome_causal(result, {"event_id": body.event_id, **manifest}, run_placebo=False, car_ablation=True)
    event_card = build_event_card(result, event={"event_id": body.event_id, **manifest})
    snap = _storage.latest_snapshot_id() or "none"
    result["event_card"] = event_card
    result["provenance"] = build_provenance(
        run_id=new_run_id("replay"),
        data_snapshot_id=snap,
        source_hashes={body.event_id: body.event_id},
        as_of_time=str(body.as_of),
    )
    REGISTRY.inc("replay_runs_total")
    return result


@app.get("/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    from market_causal_engine.case_study import list_case_studies, run_case_study

    cases = {c["case_id"]: c for c in list_case_studies()}
    if event_id not in cases:
        raise HTTPException(status_code=404, detail=f"Unknown event: {event_id}")

    result = run_case_study(event_id, as_of=120)
    meta = cases[event_id]
    snap = _storage.latest_snapshot_id() or "none"
    from market_causal_engine.counterfactuals.outcome_layer import attach_outcome_causal, build_event_card

    attach_outcome_causal(result, {"event_id": event_id, **meta}, run_placebo=False, car_ablation=True)
    card = build_event_card(result, event={"event_id": event_id, **meta})
    return {
        **card,
        "summary": {
            "ticker": meta.get("ticker"),
            "event_type": meta.get("event_type"),
            "domain": meta.get("domain"),
            "description": meta.get("description"),
        },
        "dominant_path": result.get("dominant_path", []),
        "calibrated_impact": result.get("calibrated_impact"),
        "confidence": result.get("path_attribution"),
        "provenance": build_provenance(
            run_id=new_run_id("card"),
            data_snapshot_id=snap,
            source_hashes={event_id: event_id},
            as_of_time="120",
        ),
    }


@app.get("/events/{event_id}/trace")
def get_event_trace(event_id: str, as_of: int = 120) -> dict[str, Any]:
    from market_causal_engine.case_study import run_case_study
    from market_causal_engine.platform.provenance import trace_determinism_hash

    try:
        result = run_case_study(event_id, as_of=as_of)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    trace = result.get("trace", [])
    return {
        "event_id": event_id,
        "trace": trace,
        "trace_hash": trace_determinism_hash(trace),
        "lookahead_audit": result.get("lookahead_audit"),
        "pit_audit": result.get("pit_audit"),
        "dominant_path": result.get("dominant_path", []),
    }


@app.get("/assets/{ticker}/event-risk")
def asset_event_risk(ticker: str) -> dict[str, Any]:
    from market_causal_engine.case_study import list_case_studies, run_case_study

    ticker_u = ticker.upper()
    related = [c for c in list_case_studies() if str(c.get("ticker", "")).upper() == ticker_u]
    exposures: list[dict[str, Any]] = []
    for case in related:
        r = run_case_study(case["case_id"], as_of=120)
        exposures.append(
            {
                "event_id": case["case_id"],
                "event_type": case.get("event_type"),
                "dominant_path": r.get("dominant_path", []),
                "calibrated_impact": r.get("calibrated_impact"),
            }
        )
    return {"ticker": ticker_u, "historical_events": exposures, "count": len(exposures)}


@app.get("/demo/killer/{case_id}")
def demo_killer(case_id: str, as_of: int = 120) -> dict[str, Any]:
    """Killer demo payload: timeline, path, counterfactual, neighbors, caveats."""
    from market_causal_engine.case_study import list_case_studies
    from market_causal_engine.demo.killer_demo import build_killer_demo

    cases = {c["case_id"] for c in list_case_studies()}
    if case_id not in cases:
        raise HTTPException(status_code=404, detail=f"Unknown demo case: {case_id}")
    return build_killer_demo(case_id, as_of=as_of)


@app.get("/demo/killer")
def demo_killer_default(as_of: int = 120) -> dict[str, Any]:
    from market_causal_engine.demo.killer_demo import DEFAULT_DEMO_CASE, build_killer_demo

    return build_killer_demo(DEFAULT_DEMO_CASE, as_of=as_of)


@app.get("/cases/similar")
def cases_similar(event_id: str, limit: int = 5) -> dict[str, Any]:
    from market_causal_engine.case_study import list_case_studies, run_case_study

    cases = list_case_studies()
    by_id = {c["case_id"]: c for c in cases}
    if event_id not in by_id:
        raise HTTPException(status_code=404, detail=f"Unknown event: {event_id}")

    target = run_case_study(event_id, as_of=120)
    target_path = set(target.get("dominant_path") or [])
    target_domain = by_id[event_id].get("domain")

    scored: list[tuple[float, dict[str, Any]]] = []
    for case in cases:
        if case["case_id"] == event_id:
            continue
        r = run_case_study(case["case_id"], as_of=120)
        path = set(r.get("dominant_path") or [])
        overlap = len(target_path & path) / max(len(target_path | path), 1)
        domain_bonus = 0.3 if case.get("domain") == target_domain else 0.0
        scored.append((overlap + domain_bonus, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    return {
        "event_id": event_id,
        "similar": [
            {"case_id": c["case_id"], "score": round(s, 3), "ticker": c.get("ticker"), "domain": c.get("domain")}
            for s, c in scored[:limit]
        ],
    }


class BackfillStartRequest(BaseModel):
    job_type: str = "macro_fred"
    tickers: list[str] = Field(default_factory=list)
    batch_size: int = 1
    resume_job_id: str | None = None


@app.post("/backfill/start")
def backfill_start(body: BackfillStartRequest) -> dict[str, Any]:
    with Timer("backfill_duration_seconds"):
        job = _backfill.start(
            body.job_type,
            tickers=body.tickers or None,
            batch_size=body.batch_size,
            resume_job_id=body.resume_job_id,
        )
        REGISTRY.inc("backfill_runs_total", labels={"status": job.status, "job_type": body.job_type})
        if job.status == "failed":
            raise HTTPException(status_code=502, detail=job.error or "backfill failed")
        return job.to_dict()


@app.get("/backfill/{job_id}")
def backfill_get(job_id: str) -> dict[str, Any]:
    job = _backfill.status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job.to_dict()


@app.get("/backfill")
def backfill_list(status: str | None = None, limit: int = 20) -> dict[str, Any]:
    jobs = _backfill.list_jobs(status=status, limit=limit)
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}
