# Production Roadmap: Case Demo → Continuous Data Product

**Product name:** Event Intelligence / Causal Research Assistant for Analysts  
**Not:** buy/sell predictor · alpha engine · auto-trading system  
**Is:** daily-running, auditable, point-in-time event forensics for PM / risk / IR / news desks

---

## Current vs Target

| Dimension | Today (v0.3) | Production target |
|-----------|--------------|-------------------|
| Trigger | Manual `--case-study` | Daily scheduler + on-demand API |
| Data | 9 curated cases | SEC + macro + news + market ticks, PIT-versioned |
| Validation | Case replay + calibration | 100s–1000s event benchmark + placebo/OOS |
| Interface | CLI | FastAPI + dashboard + alerts |
| Recovery | None | Queue retries, checkpoint, dead-letter |
| Audit | Trace in JSON | run_id + snapshot_id + source_hashes on every output |

**Score trajectory (honest):**

| Phase | Focus | Est. score |
|-------|-------|------------|
| P0 (this sprint) | Platform skeleton, PIT contracts, API, local pipeline | 4.5–5/10 |
| P1 (v0.5) | Postgres, EDGAR poll, FRED/BLS, news merge, market data, backfill | 5.5–6.5/10 |
| P2 (v0.6) | Event benchmark 200+, placebo/ablation/OOT harness | 6.5–7.5/10 |
| P3 | Service deploy (Postgres/Timescale, queue, K8s) | 7.5–8/10 |
| P4 | Observability, governance, human review loop | 8–8.5/10 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Scheduler (Prefect/Airflow)               │
│   daily_ingest · earnings_window · macro_calendar · health     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     Data Ingestion Layer                         │
│  SEC/EDGAR · FRED/BLS/FOMC · RSS/NewsAPI · prices/options/ETF   │
│  retry · rate-limit · source priority · raw blob → object store  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│              Point-in-Time Storage (Postgres/Timescale)          │
│  observed_time · published_time · ingested_time · revision_id    │
│  data_snapshot_id · content_hash · schema_version                │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   Evidence Compiler (existing + extended)        │
│  atoms → clusters → typed events · rejection reasons logged    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│              Causal Engine (kernel + mechanisms + calibration) │
│  path attribution · confidence · counterfactual · trace ledger   │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   FastAPI/gRPC        Dashboard            Alerting
   event cards         trace explorer       freshness / compiler / latency
```

Every API response carries **provenance**:

```json
{
  "run_id": "run_20260605_083012_a1b2",
  "model_version": "0.3.0",
  "ruleset_version": "compiler_v0.1",
  "data_snapshot_id": "snap_20260605T0800Z",
  "source_hashes": {"sec:NFLX:8-K": "sha256:..."},
  "as_of_time": "2026-06-05T08:00:00Z",
  "created_at": "2026-06-05T08:30:12Z"
}
```

---

## Pillar 1 — Continuous Data Product

**Minimal production shape (implemented in `market_causal_engine/platform/`):**

1. `DailyPipeline` — orchestrates ingest → store → compile → replay → persist run manifest
2. Checkpoint / resume via run state JSON
3. CLI: `python -m market_causal_engine.platform.cli run-daily`
4. API: `POST /events/ingest`, `POST /events/replay`, `GET /events/{id}/trace`

Case studies remain as **golden fixtures** for regression; live path uses the same compiler + kernel.

---

## Pillar 2 — Data Layer (highest priority next)

| Module | v0.3 | P1 target | Adapter |
|--------|------|-----------|---------|
| SEC/filing | `edgar_fetch` + preprocess | Auto poll, version log, retry | `platform/ingestion/sec_edgar.py` |
| News | case JSONL | RSS + NewsAPI (env key) | `platform/ingestion/news_rss.py` |
| Market | static scenario | yfinance / Polygon stub | `platform/ingestion/market_prices.py` (P1b) |
| Macro | FOMC/CPI fetch | FRED calendar + revision_id | `platform/ingestion/macro.py` |
| PIT | `published_at` on atoms | full temporal envelope on all records | `platform/pit.py` |
| Quality | partial | schema + freshness + missing + outlier | `platform/quality.py` |

**Temporal fields (required on every stored record):**

| Field | Meaning |
|-------|---------|
| `observed_time` | When the underlying fact occurred (e.g. FOMC decision instant) |
| `published_time` | When source made it public |
| `ingested_time` | When our pipeline received it |
| `revision_id` | Data revision (BLS/FRED restatements) |
| `content_hash` | Dedup + audit |

---

## Pillar 3 — Validation / Event Benchmark

Expand from 9 showcase cases to **Event Benchmark v1**:

```
benchmark/
  earnings_sp500_2016_2025.jsonl      # ~4000 events → sample 200 for v1
  short_reports_public.jsonl         # Hindenburg, Muddy Waters, Citron, Spruce Point
  macro_releases.jsonl               # CPI, FOMC, NFP, PCE, ISM
  company_shocks.jsonl               # guidance cut, fraud, FDA, CEO exit
```

Per event, run:

| Test | Purpose |
|------|---------|
| Out-of-sample replay | Train calibration on subset, test on holdout |
| Out-of-time validation | Rules frozen at T, evaluate events after T |
| Placebo days | No major event → false positive rate |
| Ablation | Drop news / SEC / price channel |
| Sensitivity | ±10% prior perturbation |
| Calibration curve | High confidence → lower path variance |
| Human review (sample) | Analyst rates path plausibility 1–5 |

Governance alignment: model inventory, validation docs, monitoring, usage boundaries (SR 11-7 / OCC 2011-12 style — documentation + controls, not regulatory claim).

Script stub: `scripts/run_benchmark.py` (P2).

---

## Pillar 4 — Product Positioning

**User:** equity analyst, PM, risk, IR, news/event desk  
**Output per event card:**

- Event summary (what happened)
- Key evidence (atoms + sources)
- Impact path (dominant mechanism chain)
- Affected assets (ticker, sector ETF, peers)
- Mechanism attribution (fundamental / sentiment / liquidity / macro)
- Confidence score + drivers
- Counterfactual scenarios (W0 vs W3…)
- Auditable trace (expandable timeline)
- Similar historical events

**Explicit non-goals:** trade signals, position sizing, execution.

---

## Pillar 5 — Engineering (service-oriented)

| Layer | v0.3 | Target |
|-------|------|--------|
| API | — | FastAPI (`market_causal_engine/api/`) |
| DB | JSON files | Postgres/Timescale (docker-compose) |
| Object store | local cache | S3-compatible (MinIO in dev) |
| Queue | sync | Redis Queue / Celery (P3) |
| Scheduler | manual | Prefect / GitHub Actions cron |
| Frontend | — | Streamlit or Next.js (P3) |
| Deploy | — | Docker → K8s/Cloud Run |

**Core API (v0.4 scaffold):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/events/ingest` | Trigger ingestion for source/ticker |
| POST | `/events/replay` | Run causal replay for event_id |
| GET | `/events/{id}` | Event card + provenance |
| GET | `/events/{id}/trace` | Full trace ledger |
| GET | `/assets/{ticker}/event-risk` | Rolling event exposure |
| GET | `/cases/similar` | Nearest neighbor in benchmark |
| GET | `/health` | Liveness + data freshness |
| GET | `/metrics` | Prometheus text format |

---

## Pillar 6 — Observability & Recovery

| Capability | Implementation |
|------------|----------------|
| Structured logs | JSON logs with `run_id`, `trace_id`, `stage` |
| Metrics | Prometheus counters/histograms in `/metrics` |
| Freshness alerts | `data_freshness_seconds{source}` gauge |
| Compiler rejections | `compiler_rejections_total{reason}` |
| Determinism check | Re-run same snapshot → hash(trace) must match |
| Daily health report | `platform/cli.py health-report` |

Trace-first product principle: **every conclusion links to evidence chain** in API + dashboard.

---

## Implementation Phases

### Step A — Honest benchmark reporting (current)

Goal: metrics reviewers can trust without reading router code.

- [x] Label tiers: real / proxy / placebo / unknown (`benchmark/label_quality.py`)
- [x] Headline vs appendix split in benchmark reports
- [x] Per-corpus real-label accuracy (no mixed overall headline)
- [x] Catalog-only EDGAR metric in every benchmark run
- [x] Naive baselines (always-neutral, majority-class)
- [x] Failed cases appendix (top 10 real-label mismatches)
- [x] [docs/validation-methodology.md](validation-methodology.md)
- [x] README headline table (real-label only)

**Next:** Teacher review checklist complete (Steps A–E).

### Step E — CI hardening + reproduce-benchmark ✅ COMPLETE

Goal: strangers can clone, run one command, and get headline metrics + manifest.

- [x] `Makefile` — `test-market`, `lint`, `reproduce-benchmark`, `reproduce-benchmark-smoke`, `docker-build`
- [x] `scripts/reproduce_benchmark.py` — pytest → PIT audit → benchmark → catalog-only → `results/reproduce/LATEST.json`
- [x] CI jobs: `lint` (ruff), `reproduce-benchmark-smoke`, `docker-build`, `market-test`, `worldcup-legacy`
- [x] Ruff config on Step A–E modules (`pyproject.toml`)
- [x] `tests/test_reproduce_benchmark.py`

```bash
make reproduce-benchmark-smoke   # CI-sized (~20 events/corpus)
make reproduce-benchmark         # full headline (200 events/corpus)
```

### Step D — World Cup split + killer demo ✅ COMPLETE

Goal: financial product stands alone; reviewers get a 5-minute NFLX walkthrough.

- [x] World Cup export script → standalone repo layout (`scripts/export_worldcup_legacy.py`)
- [x] CI split: `market-test` vs `worldcup-legacy` jobs
- [x] README leads with Problem → Demo (World Cup demoted to [docs/worldcup-split.md](worldcup-split.md))
- [x] Killer demo builder (`market_causal_engine/demo/killer_demo.py`)
- [x] Static HTML export (`demo/static/`) + Streamlit (`demo/streamlit_app.py`)
- [x] API: `GET /demo/killer/{case_id}`

### Step C — PIT data hardening ✅ COMPLETE

Goal: every evidence atom carries a full temporal envelope; replays are auditable for look-ahead.

- [x] `platform/pit_hardening.py` — `CaseTimeAxis`, atom↔PIT bridge, `PITAuditReport`
- [x] Temporal envelope on atoms: `observed_time`, `published_time`, `ingested_time`, `revision_id`
- [x] `pit_audit` on every case-study / catalog-feed replay (alongside `lookahead_audit`)
- [x] Extraction pipeline enriches atoms with temporal metadata before write
- [x] Benchmark report includes `pit_compliance` for case-study fixtures
- [x] `scripts/audit_pit_compliance.py` — batch audit CLI
- [x] API trace exposes `pit_audit`

Auto-enrichment uses manifest `time_axis.origin_timestamp_et` (catalog: `filing_date` fallback).

### Step B — Causal outcome layer ✅ COMPLETE

Goal: every event outputs testable econometric outcomes, not just paths.

- [x] Mandatory `outcome_causal` on replay: AR, factor-adjusted, SC, placebo CI (`outcome_layer.py` + `replay_event`)
- [x] Event-study metrics: CAR, AAR, t-stat, bootstrap/placebo CI
- [x] Ablation tied to marginal CAR contribution per channel (`car_ablation.py` + validation suite)
- [x] API event card includes counterfactual block (`GET /events/{id}`, `POST /events/replay`)

Code in `counterfactuals/` is wired to the main replay path; corpus cache is used when present.
CAR ablation auto-runs on case studies / API; bulk earnings replay skips channel ablation for cost.

### P0 — Platform skeleton (current sprint)

- [x] `platform/pit.py` — PIT record envelope
- [x] `platform/provenance.py` — run manifest
- [x] `platform/ingestion/*` — SEC, macro, RSS adapters
- [x] `platform/storage/local.py` — versioned local store (dev)
- [x] `platform/pipeline.py` — daily pipeline with checkpoint
- [x] `platform/quality.py` — schema + freshness checks
- [x] `api/app.py` — FastAPI scaffold
- [x] `observability/` — logging + metrics hooks
- [x] `docker-compose.yml` — postgres + redis + api
- [x] `.github/workflows/ci.yml`

### P1 — Data layer (complete in v0.5)

- [x] Postgres/Timescale migrations for PIT tables (`platform/db/migrations/001_pit_schema.sql`)
- [x] `PostgresPlatformStore` + `get_platform_store()` factory
- [x] EDGAR polling job + filing diff detection (`EdgarPollIngestor` + `filing_versions`)
- [x] FRED/BLS revision tracking (`FredBlsIngestor` + `macro_series_points`)
- [x] NewsAPI + RSS multi-source merge (`NewsMergedIngestor`)
- [x] Market data: daily + intraday bars, sector ETF, options IV stub (`MarketPricesIngestor`)
- [x] Backfill runner with progress table (`BackfillRunner` + CLI/API)

### P2 — Benchmark & validation (v0.6)

- [x] 3194-event earnings catalog with **1998 Yahoo real labels** (1196 pre-IPO/missing bars retain proxy)
- [x] Short report / macro / shock / placebo corpora
- [x] `market_causal_engine/benchmark/` — replay, metrics, OOT, placebo, ablation
- [x] `scripts/run_benchmark.py --run --max-events 200`
- [x] Human review CSV export
- [ ] Replace remaining 1196 missing-bar proxy labels (IPO date filter / vendor prices)

### P3 — Production deploy (4 weeks)

- Redis Queue workers for ingest/replay
- Prefect flows for daily + earnings season
- Streamlit dashboard (event cards + trace viewer)
- GitHub Actions → container registry → staging

### P5 — Causal identification & learned calibration (v0.7)

- [x] **Phase 1: Market econometric counterfactuals**
  - `market_causal_engine/counterfactuals/` — abnormal_return, factor_model, synthetic_control, placebo
  - `scripts/run_counterfactuals.py --full` — 9 case studies (SC + placebo) + 1998 earnings events (AR)
  - Static bars fallback for delisted tickers (e.g. NKLA) in `data/market/counterfactuals/static_bars/`
  - Output: `data/benchmark/counterfactuals/*.jsonl`, per-case `outcome_causal.json`
- [x] **Phase 2: Causal claim extractor (LLM propose + schema validate)**
  - `market_causal_engine/extraction/` — `causal_claim_extractor`, `llm_extractor`, `rule_validator`, `atom_scorer`
  - `scripts/run_causal_claims.py --cases` — 9 case studies → `causal_claims.json`
  - LLM optional (`--use-llm`); default heuristic proposer + strict schema/timing validation
- [x] **Phase 3: Mechanism calibration (learned weights vs Phase 1 `effect`)**
  - `market_causal_engine/calibration/` — feature_builder, mechanism_model, bayesian_calibrator, evaluation, runner
  - `scripts/run_mechanism_calibration.py --full` — train on 9 cases + 188 major events, calibrate per case
  - Output: `mechanism_model.json`, per-case `mechanism_calibration.json`
- [x] **Learned runtime layer (replaces rule/heuristic defaults)**
  - `market_causal_engine/learned/` — store, propagation, direction, severity, compiler_scorer
  - `market_causal_engine/calibration/fit_learned.py` + `scripts/fit_learned_stack.py` — export `data/market/learned/*` + `mechanisms_v0.2_learned.json`
  - Wired into kernel `commit()`, compiler `select_best_rule()`, replay direction, analysis path attention, case study calibration attach
- [x] **Earnings replay calibration (v0.8)**
  - Event-aware scenario severity scaling (`magnitude_bucket` + `is_major_event`) for mild/neutral earnings
  - Direction inference: kernel risk primary, trace pressure bias, E1/E2 scenario polarity, no `observed_outcomes` leak
  - Posterior writeback into `mechanisms_v0.2_learned.json`; `earnings_call_transcript` uses `k.prior()`
  - Benchmark earnings direction **94%** (100-event smoke; mild events scaled to neutral); placebo FP 0%
- [x] **Catalog feed expansion (v0.9)**
  - `benchmark/catalog/queue.py` — benchmark-sample prioritization, `--missing-only`, `--benchmark-sample`, `--coverage`
  - Improved 8-K scoring: penalize proxy/officer-change filings (Item 5.02/5.07)
  - Batch: `python scripts/build_catalog_atoms.py --benchmark-sample --missing-only --real-labels-only --max N`
- [x] **Earnings interaction magnitude model (v0.9)**
  - `feature_builder.expand_earnings_interactions()` + `EARNINGS_FEATURE_ORDER` (6 interaction terms)
  - `learned/magnitude.py` → `calibrate_final_risk()` for earnings return % (replaces kernel-only linear scale)
  - Export: `data/market/learned/earnings_magnitude.json`; refit via `scripts/fit_learned_stack.py`
- [x] **Catalog feed direction (v1.2)** — superseded by Phase 4 below
  - Heuristic keyword polarity + confidence gating; catalog-only ~45% direction
- [x] **Phase 4: Catalog learned stack (claims → domain model → router)**
  - `benchmark/catalog/claims.py` — Phase 2 causal claims per catalog event
  - `benchmark/catalog/fit_learned.py` — fit `catalog_domain_model.json` + `catalog_router.json`
  - `benchmark/catalog/router.py` — learned catalog vs scenario router
  - `learned/direction.py` — catalog_feed uses domain model + claim polarity consensus (disagree → neutral)
  - `benchmark/replay.py` — router replaces `confidence.py` gating
  - `benchmark/catalog/direction_model.py` — learned 3-way direction classifier + kernel fallback
  - Enhanced Phase 2 claim proposer (`extraction/llm_extractor.py`) with polarity-tagged earnings patterns
  - Batch: `python scripts/run_catalog_causal_claims.py --all --missing-only --use-llm` (new atoms only)
  - LLM config: `ZHISUAN_API_KEY` + `OPENAI_BASE_URL=https://ai.azya.top/v1` + `OPENAI_MODEL=qwen3.5` (see `.env.example`)
  - Fit: `python scripts/fit_catalog_learned.py` (default: LLM-only quality policy, no heuristic)
  - Quality policy (default): LLM-only, `min_claims≥2`, `conf≥0.5`, `|pol|≥0.1`, `|net|≥0.08`, cap 4 claims, drop atom-fallback
  - Full pipeline: `python scripts/run_catalog_quality_pipeline.py` (heuristic LLM → up to 2 fallback rounds → fit → eval)
  - Fit only: `python scripts/fit_catalog_learned.py --allow-atom-fallback`
  - Claim quality: evidence-based polarity refine, generic-effect rewrite, mechanism-specific effects
  - Offline refine: `python scripts/refine_catalog_claims.py` (no API)
  - LLM re-extract refresh: `python scripts/run_catalog_causal_claims.py --all --use-llm --force --quality-refresh`
  - Strict policy (`llm_event` only): **840** eligible on full reproduce; catalog-only **58.81%** (domain+polarity consensus)


- Model inventory doc + change log
- Determinism CI gate
- Grafana dashboards
- On-call runbook + daily health email

---

## How to run (dev)

```bash
# Install with API/platform extras
pip install -e ".[dev,platform,api]"

# Fit learned stack (Phase 1-3 → runtime artifacts)
python scripts/fit_learned_stack.py

# Build EDGAR catalog atoms (benchmark sample first, skip existing)
python scripts/build_catalog_atoms.py --coverage
python scripts/build_catalog_atoms.py --benchmark-sample --missing-only --real-labels-only --max 200

# Fit catalog learned stack (Phase 4 — requires claims + atoms)
# Optional: copy .env.example → .env and set ZHISUAN_API_KEY
python scripts/run_catalog_causal_claims.py --all --benchmark-sample --force --use-llm
python scripts/fit_catalog_learned.py

# Run daily pipeline locally (uses data/platform_store/)
python -m market_causal_engine.platform.cli run-daily

# Start API
uvicorn market_causal_engine.api.app:app --reload --port 8080

# Docker stack
docker compose up -d
curl http://localhost:8080/health
```

---

## Success criteria for "production-ready v1"

1. Pipeline runs unattended daily for 30 days with <1% unrecoverable failures
2. ≥200 events in benchmark with documented OOS metrics
3. Placebo false-positive rate <5% on quiet days
4. Every API response includes full provenance block
5. p95 replay latency <30s for single event
6. Analyst review: median path plausibility ≥3.5/5 on 50-event sample
