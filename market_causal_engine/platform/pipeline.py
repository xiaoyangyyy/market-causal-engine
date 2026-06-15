"""Daily production pipeline: ingest → store → compile → replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_causal_engine.platform.ingestion.base import IngestContext, Ingestor, IngestResult
from market_causal_engine.platform.ingestion.defaults import default_ingestors
from market_causal_engine.platform.pit import PITRecord
from market_causal_engine.platform.provenance import RunManifest, new_run_id
from market_causal_engine.platform.quality import validate_records
from market_causal_engine.platform.storage.base import PlatformStore
from market_causal_engine.platform.storage.factory import get_platform_store


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _snapshot_id_from_time(as_of: str) -> str:
    compact = as_of.replace("-", "").replace(":", "")[:15]
    return f"snap_{compact}Z"


@dataclass
class PipelineResult:
    run_id: str
    snapshot_id: str
    ingest_results: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    event_cards: list[dict[str, Any]] = field(default_factory=list)
    status: str = "succeeded"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "ingest_results": self.ingest_results,
            "quality": self.quality,
            "event_cards": self.event_cards,
            "status": self.status,
            "error": self.error,
        }


class DailyPipeline:
    """Production orchestrator: ingest → quality → PIT store → replay."""

    def __init__(
        self,
        *,
        storage: PlatformStore | None = None,
        ingestors: list[Ingestor] | None = None,
        store_root: Path | None = None,
    ) -> None:
        self.storage = storage or get_platform_store(store_root=store_root)
        self.ingestors = ingestors if ingestors is not None else default_ingestors(self.storage)

    def run(
        self,
        *,
        as_of_time: str | None = None,
        run_id: str | None = None,
        tickers: list[str] | None = None,
        skip_network_ingest: bool = False,
        replay_cases: bool = True,
    ) -> PipelineResult:
        as_of = as_of_time or _utc_now_iso()
        rid = run_id or new_run_id("daily")
        snapshot_id = _snapshot_id_from_time(as_of)

        manifest = RunManifest(run_id=rid, data_snapshot_id=snapshot_id, as_of_time=as_of)
        self.storage.save_manifest(manifest)

        ctx = IngestContext(run_id=rid, as_of_time=as_of, tickers=tickers or [])
        all_records: list[PITRecord] = []
        ingest_summaries: list[dict[str, Any]] = []

        try:
            for ingestor in self.ingestors:
                if skip_network_ingest and ingestor.source_kind.value != "manual":
                    manifest.add_stage(ingestor.source_kind.value, status="skipped", detail={"reason": "skip_network"})
                    continue
                result: IngestResult = ingestor.ingest(ctx)
                ingest_summaries.append(result.to_dict())
                all_records.extend(result.records)
                manifest.add_stage(
                    ingestor.source_kind.value,
                    status="ok" if result.ok else "partial",
                    detail=result.to_dict(),
                )

            quality = validate_records(all_records, as_of_time=as_of)
            manifest.add_stage("quality", status="ok" if quality.ok else "failed", detail=quality.to_dict())
            if not quality.ok:
                manifest.status = "failed"
                manifest.error = "quality gate rejected records"
                self.storage.save_manifest(manifest)
                return PipelineResult(
                    run_id=rid,
                    snapshot_id=snapshot_id,
                    ingest_results=ingest_summaries,
                    quality=quality.to_dict(),
                    status="failed",
                    error=manifest.error,
                )

            accepted = [
                r
                for r in all_records
                if not any(i.severity == "error" and i.record_id == r.record_id for i in quality.issues)
            ]

            stored = self.storage.save_records(snapshot_id, accepted)
            manifest.source_hashes = {r.source_id: r.content_hash for r in accepted}
            manifest.add_stage("store", status="ok", detail={"stored": stored, "snapshot_id": snapshot_id})

            event_cards: list[dict[str, Any]] = []
            if replay_cases:
                event_cards = self._replay_case_library(as_of_time=as_of, run_id=rid, snapshot_id=snapshot_id)
                manifest.add_stage("replay", status="ok", detail={"event_cards": len(event_cards)})

            manifest.status = "succeeded"
            self.storage.save_manifest(manifest)

            return PipelineResult(
                run_id=rid,
                snapshot_id=snapshot_id,
                ingest_results=ingest_summaries,
                quality=quality.to_dict(),
                event_cards=event_cards,
                status="succeeded",
            )
        except Exception as exc:  # noqa: BLE001
            manifest.status = "failed"
            manifest.error = str(exc)
            manifest.add_stage("pipeline", status="failed", detail={"error": str(exc)})
            self.storage.save_manifest(manifest)
            return PipelineResult(
                run_id=rid,
                snapshot_id=snapshot_id,
                ingest_results=ingest_summaries,
                status="failed",
                error=str(exc),
            )

    def _replay_case_library(
        self,
        *,
        as_of_time: str,
        run_id: str,
        snapshot_id: str,
    ) -> list[dict[str, Any]]:
        from market_causal_engine.case_study import list_case_studies, run_case_study
        from market_causal_engine.platform.provenance import build_provenance as prov

        cards: list[dict[str, Any]] = []
        for case in list_case_studies()[:5]:
            case_id = case["case_id"]
            try:
                result = run_case_study(case_id, as_of=120)
                cards.append(
                    {
                        "event_id": case_id,
                        "ticker": case.get("ticker"),
                        "event_type": case.get("event_type"),
                        "domain": case.get("domain"),
                        "dominant_path": result.get("dominant_path", []),
                        "calibrated_impact": result.get("calibrated_impact"),
                        "provenance": prov(
                            run_id=run_id,
                            data_snapshot_id=snapshot_id,
                            source_hashes={case_id: case_id},
                            as_of_time=as_of_time,
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                cards.append({"event_id": case_id, "error": str(exc)})
        return cards

    def resume(self, run_id: str) -> PipelineResult | None:
        manifest = self.storage.load_manifest(run_id)
        if not manifest:
            return None
        return PipelineResult(
            run_id=manifest.run_id,
            snapshot_id=manifest.data_snapshot_id,
            status=manifest.status,
            error=manifest.error,
        )
