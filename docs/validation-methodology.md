# Validation Methodology

This document defines **which metrics are headline-worthy** and how to reproduce them. It exists so reviewers can audit claims without reading the full codebase.

## Product claim (what we prove)

> Under point-in-time constraints, the engine reconstructs **auditable mechanism paths** from pre-event evidence and compares simulated impact to **observed market outcomes** — without claiming alpha or trade signals.

We do **not** claim omniscient direction prediction. We claim **forensic explainability** with **econometric outcome checks** (Phase B, in progress).

---

## Label tiers

Every benchmark event is classified before scoring:

| Tier | Definition | Used in headline? |
|------|------------|-------------------|
| **real** | Yahoo daily close, case-study manual labels, short/macro curated outcomes | Yes |
| **proxy** | `metadata.synthetic_labels=true` — scenario-derived stand-ins | No (appendix only) |
| **placebo** | Quiet days — false-positive control | Yes (FP rate only) |
| **unknown** | Missing or unverified label source | No |

Implementation: `market_causal_engine/benchmark/label_quality.py`

---

## Headline metrics (README / external)

Report **only** these as primary results:

1. **Catalog-only direction accuracy**  
   - Corpus: `earnings_sp500_2016_2025` with quality-filtered LLM claims  
   - Replay: `catalog_feed` only — **no scenario router**  
   - Script: `python -c "from market_causal_engine.benchmark.catalog_eval import eval_catalog_only_metrics; ..."`  
   - Current: **58.81%** on **840** eligible events (3-way: up/down/neutral; `make reproduce-benchmark`)

2. **Real-label direction accuracy (by corpus)**  
   - Split: earnings / short_report / macro / company_shocks — **never mixed overall**  
   - Excludes proxy labels  
   - Script: `python scripts/run_benchmark.py --run --max-events 200`  
   - Read: `results/benchmark/{run_id}_report.md` → **Headline metrics** section

3. **Placebo false-positive rate**  
   - Corpus: `placebo_quiet_days`  
   - Target: < 5%  
   - Event flagged FP if drawdown ≥ 0.35 or |pressure| ≥ 0.20 on quiet day

4. **Naive baselines (real-label)**  
   - Always-neutral accuracy  
   - Always-majority-class accuracy  
   - Model must beat these on real-label subsets to claim signal

5. **Out-of-time (OOT) test accuracy**  
   - Train: events before cutoff (default `2022-01-01`)  
   - Test: events on/after cutoff  
   - Filter: **real-label only**

---

## Appendix metrics (not headline)

Keep for regression tracking but **do not cite externally**:

| Metric | Why excluded |
|--------|--------------|
| Mixed overall direction accuracy (~99%) | Router defaults to scenario E1/E2; not catalog forensics |
| Proxy-label earnings accuracy | Synthetic stand-ins for missing price bars |
| Macro n=6 accuracy | Too few events for statistical claims |

Report location: `_report.md` → **Appendix — mixed / legacy**

---

## Replay paths

| Path | When used | Honest metric |
|------|-----------|---------------|
| `catalog_feed` | EDGAR atoms + effective LLM claims | Catalog-only eval |
| `scenario` (E1/E2) | Template earnings shock | Scenario-router path accuracy |
| `case_study` | 9 golden fixtures | Case regression |
| `placebo` | Quiet-day control | FP rate |

Router behavior: for earnings with catalog claims, router compares catalog vs scenario features and usually picks **scenario** (safe default). Hence overall benchmark ≠ catalog capability.

---

## Failed cases (public appendix)

Each benchmark run exports up to **10 real-label direction mismatches**:

- File: `results/benchmark/{run_id}_failed_cases.md`
- Includes: event_id, observed vs simulated direction, router choice, replay mode

Publishing failures increases credibility vs cherry-picking successes.

---

## Reproduce headline table

```bash
pip install -e ".[dev]"

# Full benchmark suite (headline + appendix + failed cases)
python scripts/run_benchmark.py --run --max-events 200

# Catalog-only honest metric
python -c "
from market_causal_engine.benchmark.catalog_eval import eval_catalog_only_metrics
import json
print(json.dumps(eval_catalog_only_metrics(), indent=2))
"
```

---

## Step B — Causal outcome layer ✅

Every replay attaches `outcome_causal` (AR / factor-adjusted / SC, placebo rank, event-study CAR/AAR/t-stat/CI).

**CAR ablation** (`counterfactuals/car_ablation.py`):

- Ablate evidence channels: `no_news`, `no_sec`, `no_price`
- `marginal_return_pct = baseline_predicted − ablated_predicted`
- `share_of_observed_car = marginal_return_pct / observed_CAR_pct`
- Auto on case-study replays and API; benchmark ablation suite reports `car_by_channel` + `car_by_case`

Existing code: `market_causal_engine/counterfactuals/` — wired to every replay via `attach_outcome_causal()`.

See [production-roadmap.md](production-roadmap.md) → **Step E** (next).

---

## Step D — World Cup split + killer demo ✅

- **World Cup legacy:** export with `python scripts/export_worldcup_legacy.py` → [docs/worldcup-split.md](worldcup-split.md)
- **Killer demo:** NFLX 2022 Q1 — `python scripts/export_killer_demo.py` → `demo/static/`
- **API:** `GET /demo/killer/nflx_2022q1_earnings`

---

## Step C — PIT data hardening ✅

Every admissible atom must have a full temporal envelope and pass PIT quality gates at replay time.

- **Envelope fields:** `observed_time`, `published_time`, `ingested_time`, `revision_id`, `content_hash`
- **Replay audit:** `pit_audit` block (coverage, violations, pass/fail) on case-study and catalog-feed replays
- **Batch audit:** `python scripts/audit_pit_compliance.py`
- **Bridge:** `atom_to_pit_record()` maps feed atoms → `PITRecord` for platform storage

Existing contracts: `platform/pit.py`, `platform/quality.py`, `lookahead.py`.

---

## Step E — CI + reproduce-benchmark ✅

```bash
make test-market
make lint
make reproduce-benchmark-smoke
```

Manifest: `results/reproduce/LATEST.json` — headline table, PIT audit, benchmark artifacts.

CI runs: lint · market-test · reproduce-benchmark-smoke · docker-build · worldcup-legacy (isolated).

---

## Governance

- Not investment advice  
- Not a trading signal  
- All conclusions must link to provenance (`run_id`, `source_hashes`, `as_of_time`)  
- Proxy labels documented and excluded from headline
