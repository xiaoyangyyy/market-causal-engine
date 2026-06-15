# Market Event Causal Engine

Trace-first **market event causal forensics** — compiles SEC filings, news, and market signals into auditable impact pathways. **Not a buy/sell predictor.**

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

## Event benchmark (P2)

3194 earnings + placebo / macro / short-report corpora under `data/benchmark/`.

```bash
python scripts/run_benchmark.py --list
python scripts/run_benchmark.py --run --max-events 200 --until 120
python scripts/run_benchmark.py --run --corpus earnings_sp500_2016_2025 --max-events 200 --sensitivity
```

Outputs: `results/benchmark/{run_id}.json`, `_report.md`, `_human_review.csv` (analyst rating export).

Metrics: direction accuracy, out-of-time split, placebo false-positive rate, channel ablation (no_news / no_sec / no_price).


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
python -m pytest tests/ -q   # 170+ tests
```

## Project structure

```
market_causal_engine/     # Kernel, mechanisms, extraction, case studies
  platform/               # PIT storage, ingestion, daily pipeline
  api/                    # FastAPI service
  observability/          # Structured logs + Prometheus metrics
data/market/              # Scenarios, case studies, compiler rules, calibration
data/platform_store/      # Local PIT snapshots (dev, gitignored)
worldcup_causal_engine/   # Legacy World Cup crowd-risk engine (same repo)
docs/
tests/
```

---

## Legacy: World Cup Causal Engine

The original **World Cup crowd-risk** runtime remains in `worldcup_causal_engine/` for media-opinion and stadium safety simulation (S1–S6, Qatar 2022 calibration).

```bash
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W0 --until 120 --explain
```

See [docs/00-完整方案.md](docs/00-完整方案.md) and [docs/experiment-report.md](docs/experiment-report.md).
