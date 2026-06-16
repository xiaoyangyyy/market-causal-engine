# Market Event Causal Engine

Trace-first **market event causal forensics** — compiles SEC filings, news, and market signals into auditable impact pathways. **Not a buy/sell predictor.**

**Problem:** After a major market event, analysts need to explain *what moved the stock* under point-in-time constraints — without leaking future headlines or inflating accuracy with proxy labels.

**Solution:** Evidence atoms → causal kernel → econometric counterfactual (CAR, synthetic control, placebo) + honest benchmark reporting.

## Killer demo (5 minutes)

**NFLX Q1 2022** — subscriber miss, ~25% after-hours, full forensic card:

```bash
pip install -e ".[dev]"
python scripts/export_killer_demo.py
python -m http.server 8765 --directory demo/static
# → http://localhost:8765

# Interactive UI
pip install -e ".[demo]"
python scripts/run_killer_demo.py
```

See [demo/README.md](demo/README.md) · API: `GET /demo/killer/nflx_2022q1_earnings`

---

**Product positioning:** Event Intelligence / Causal Research Assistant for analysts (PM, risk, IR, news desks).

Three product lines:

| Line | Scenarios | Focus |
|------|-----------|-------|
| **Earnings** | E1, E2 | 财报冲击路径 · 基本面/情绪/流动性贡献 · 9 历史 case |
| **Short Report** | S1, S2 | 做空报告 · 信任/流动性 · squeeze & fraud cases |
| **Macro** | X1, X2 | FOMC/CPI → sector → stock 传导 |

## Production platform (v0.5 — P1 data layer)

Continuous data product — see [docs/production-roadmap.md](docs/production-roadmap.md).

```bash
pip install -e ".[dev,platform,api]"

# Apply schema (Postgres when DATABASE_URL set, else local store)
python -m market_causal_engine.platform.cli migrate

# Daily pipeline (RSS + FRED + EDGAR poll + market bars)
python -m market_causal_engine.platform.cli run-daily --offline   # skip network
python -m market_causal_engine.platform.cli run-daily             # live ingest

# Resumable backfill
python -m market_causal_engine.platform.cli backfill start macro_fred
python -m market_causal_engine.platform.cli backfill status --list

python -m market_causal_engine.platform.cli health-report

# API service
uvicorn market_causal_engine.api.app:app --reload --port 8080

# Docker (Postgres + Timescale + API auto-migrate)
docker compose up -d
```

Env vars: `DATABASE_URL`, `FRED_API_KEY`, `NEWSAPI_KEY` — see `.env.example`.

## Validation (headline metrics — real-label only)

**Problem → solution:** Existing tools mix scenario templates with observed outcomes and report inflated overall accuracy. This engine separates **forensic path quality** from **econometric outcome validation**.

| Metric | What it measures | Current (honest) |
|--------|------------------|------------------|
| **Catalog-only direction** | EDGAR atoms + LLM claims, no scenario router | **58.81%** (840 quality-eligible events) |
| **Real-label benchmark** | Yahoo daily / case-study observed direction | See latest `_report.md` headline section |
| **Placebo FP rate** | Quiet days with no major event | Target < 5% |
| **Naive baseline** | Always-neutral / majority-class | Reported alongside model |

Do **not** use mixed-corpus overall accuracy (~99%) as headline — it is router-dominated and includes proxy labels. See [docs/validation-methodology.md](docs/validation-methodology.md).

## Reproduce headline metrics (Step E)

One command regenerates headline table + audit manifest:

```bash
pip install -e ".[dev,platform,api]"
make reproduce-benchmark-smoke    # ~5–15 min (CI default)
make reproduce-benchmark          # full 200 events/corpus
```

Output: `results/reproduce/LATEST.json` with `headline_table`, PIT compliance, benchmark `run_id`, artifact paths.

See [docs/validation-methodology.md](validation-methodology.md).

## Event benchmark (P2)

3194 earnings + placebo / macro / short-report corpora under `data/benchmark/`.

```bash
python scripts/run_benchmark.py --list
python scripts/run_benchmark.py --run --max-events 200 --until 120
python scripts/run_benchmark.py --run --corpus earnings_sp500_2016_2025 --max-events 200 --sensitivity
```

Outputs: `results/benchmark/{run_id}.json`, `_report.md` (headline vs appendix), `_failed_cases.md`, `_human_review.csv`.

Metrics: **real-label direction accuracy by corpus**, catalog-only EDGAR path, OOT split, placebo FP, naive baselines, channel ablation.


## Case study CLI (research / regression fixtures)

```bash
pip install -r requirements.txt

python -m market_causal_engine.main --list-domains
python -m market_causal_engine.main --scenario-id E1 --world W0 --explain

# Historical case study (look-ahead safe)
python -m market_causal_engine.main --list-case-studies
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --as-of 120 --explain

# Extract atoms from SEC/news sources
python -m market_causal_engine.main --extract-all
python -m market_causal_engine.main --fetch-edgar nflx_2022q1_earnings
python -m market_causal_engine.main --fetch-macro fomc_2022_75bp
```

## Case library (9)

NFLX, SNAP, META, SHOP · Hindenburg/NKLA, GME squeeze, Luckin fraud · FOMC 75bp, CPI hot print

See [docs/case-study-methodology.md](docs/case-study-methodology.md) and [docs/00-market-causal-engine.md](docs/00-market-causal-engine.md).

## Tests

```bash
make test-market              # or: python -m pytest tests/ -q ...
make reproduce-benchmark-smoke
```

## Project structure

```
market_causal_engine/     # Kernel, mechanisms, extraction, case studies, demo
  platform/               # PIT storage, ingestion, daily pipeline
  api/                    # FastAPI service
  demo/                   # Killer demo builder
demo/static/              # Exported NFLX demo (HTML + JSON)
Makefile                  # test, lint, reproduce-benchmark
docs/
tests/
```

World Cup legacy (`worldcup_causal_engine/`) is **deprecated in this repo** — export via `scripts/export_worldcup_legacy.py`. See [docs/worldcup-split.md](docs/worldcup-split.md).
