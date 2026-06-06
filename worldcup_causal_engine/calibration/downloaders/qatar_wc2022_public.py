"""Curated public post-hoc facts for Qatar FIFA World Cup 2022.

Sources are documented in docs/calibration-data-sources.md.
Values are normalized risk proxies in [0,1], not literal probabilities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldcup_causal_engine.calibration.downloaders.base import DownloadResult
from worldcup_causal_engine.calibration.downloaders.gdelt_doc import (
    fetch_timeline_volume,
    timeline_stats,
)


@dataclass(frozen=True)
class PublicFact:
    fact_id: str
    scenario_proxy: str  # S1 | S2 | S3
    source: str
    url: str
    notes: str
    observations: list[dict[str, Any]] = field(default_factory=list)


PUBLIC_FACTS: list[PublicFact] = [
    PublicFact(
        fact_id="japan_spain_var_dec2022",
        scenario_proxy="S1",
        source="BBC Sport / FIFA post-hoc VAR release",
        url="https://www.bbc.co.uk/sport/football/63832775",
        notes="High global media controversy; no major offline fan violence reported in Qatar.",
        observations=[
            {"key": "rumor_volume_index", "value": 0.82, "weight": 1.5, "time_bucket": "final"},
            {"key": "verbal_conflict", "value": 0.08, "weight": 2.0, "time_bucket": "final"},
            {"key": "scuffle", "value": 0.02, "weight": 1.0, "time_bucket": "final"},
            {"key": "riot", "value": 0.0, "weight": 1.0, "time_bucket": "final"},
        ],
    ),
    PublicFact(
        fact_id="brazil_eliminated_croatia_dec2022",
        scenario_proxy="S2",
        source="Tournament reports; Qatar MoI no major crimes",
        url="https://thepeninsulaqatar.com/article/07/12/2022/no-major-security-incident-recorded-the-safest-fifa-world-cup-so-far-says-security-authorities",
        notes="Elimination grief + gatherings; still no major security-disturbing crimes in host country.",
        observations=[
            {"key": "verbal_conflict", "value": 0.22, "weight": 1.5, "time_bucket": "final"},
            {"key": "scuffle", "value": 0.06, "weight": 1.0, "time_bucket": "final"},
            {"key": "panic", "value": 0.05, "weight": 0.8, "time_bucket": "final"},
        ],
    ),
    PublicFact(
        fact_id="fan_zone_overcrowding_nov2022",
        scenario_proxy="S3",
        source="AP/NBC/CBC fan festival reports + MoI press",
        url="https://www.nbcnews.com/news/us-news/day-fifa-world-cup-qatar-faces-overcrowding-troubles-rcna58033",
        notes="Al Bidda fan zone crush pressure; tournament-wide no major crimes but high crowd stress.",
        observations=[
            {"key": "panic", "value": 0.48, "weight": 2.0, "time_bucket": "final"},
            {"key": "verbal_conflict", "value": 0.12, "weight": 1.2, "time_bucket": "final"},
            {"key": "scuffle", "value": 0.08, "weight": 1.0, "time_bucket": "final"},
            {"key": "riot", "value": 0.05, "weight": 0.8, "time_bucket": "final"},
        ],
    ),
    PublicFact(
        fact_id="qatar_moi_security_summary_dec2022",
        scenario_proxy="S3",
        source="Qatar SSOC / Peninsula Qatar",
        url="https://thepeninsulaqatar.com/article/07/12/2022/no-major-security-incident-recorded-the-safest-fifa-world-cup-so-far-says-security-authorities",
        notes="585,606 NCC calls; no major security-disturbing crimes — caps riot/verbal upper bound.",
        observations=[
            {"key": "riot", "value": 0.02, "weight": 1.5, "time_bucket": "final"},
            {"key": "verbal_conflict", "value": 0.10, "weight": 1.0, "time_bucket": "final"},
        ],
    ),
]

SCENARIO_MAP = {
    "S1": "S1_controversial_call_high_density",
    "S2": "S2_team_eliminated_transit_delay",
    "S3": "S3_heat_crowd_comm_delay",
}


class QatarWC2022Downloader:
    """Fetch/cache public calibration inputs for Qatar 2022."""

    source = "qatar_wc2022_public"

    def __init__(self, raw_dir: str | Path = "data/calibration_raw"):
        self.raw_dir = Path(raw_dir)

    def fetch(self, *, out_dir: str | Path | None = None, query: dict[str, Any] | None = None) -> DownloadResult:
        out = Path(out_dir or self.raw_dir)
        out.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        facts_path = out / "qatar_wc2022_public_facts.json"
        payload = {
            "source": self.source,
            "facts": [
                {
                    "fact_id": f.fact_id,
                    "scenario_proxy": f.scenario_proxy,
                    "source": f.source,
                    "url": f.url,
                    "notes": f.notes,
                    "observations": f.observations,
                }
                for f in PUBLIC_FACTS
            ],
        }
        facts_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(str(facts_path))

        enrich = (query or {}).get("enrich_gdelt", True)
        if enrich:
            gdelt_specs = [
                ("japan_spain_var", "Japan Spain VAR World Cup", "20221201120000", "20221203120000"),
                ("fan_zone", "Qatar World Cup fan zone", "20221119120000", "20221121120000"),
            ]
            for name, q, start, end in gdelt_specs:
                cache = out / f"gdelt_{name}.json"
                try:
                    data = fetch_timeline_volume(q, start=start, end=end, cache_path=cache)
                    stats = timeline_stats(data)
                    sidecar = out / f"gdelt_{name}_stats.json"
                    sidecar.write_text(json.dumps(stats, indent=2), encoding="utf-8")
                    files.append(str(cache))
                    files.append(str(sidecar))
                except Exception as e:  # noqa: BLE001
                    err = out / f"gdelt_{name}_error.txt"
                    err.write_text(str(e), encoding="utf-8")
                    files.append(str(err))

        return DownloadResult(source=self.source, files=files, meta={"facts": len(PUBLIC_FACTS)})
