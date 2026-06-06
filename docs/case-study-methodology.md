# Case Study Methodology

Historical case studies replay **public evidence atoms** through the compiler and causal kernel. Observed market returns are **comparison labels only** — never simulation inputs.

## Principles

1. **Feed-only replay** — Case scenarios have no synthetic `trigger` events. All shocks enter via compiled atoms.
2. **Atom ≠ Event** — Raw text/market observations compile to typed events before touching state.
3. **Look-ahead safe** — Each atom carries `published_at` (minute on case timeline). At simulation horizon `as_of`, atoms with `published_at > as_of` are **rejected**.
4. **Post-hoc forbidden** — Atoms tagged `source_class: next_day_only | post_mortem | calibration_label` are blocked in strict mode.

## Atom schema (JSONL)

```json
{
  "atom_id": "NFLX22Q1_001",
  "text": "Netflix reports Q1 subscriber loss...",
  "source": "8-K",
  "time": 0,
  "published_at": 0,
  "tags": ["earnings"],
  "metadata": {
    "severity": 0.92,
    "miss_severity": 0.95,
    "source_class": "primary_filing"
  }
}
```

| Field | Meaning |
|-------|---------|
| `time` | Event reference minute (when the fact pertains to) |
| `published_at` | When the evidence became publicly available (must be ≤ `as_of` to enter kernel) |
| `metadata.source_class` | `next_day_only` / `calibration_label` blocked in strict replay |
| `metadata.available_from` | Optional explicit availability minute |
| `metadata.uses_future_price` | If true, atom is always rejected (price leak) |

## Look-ahead rejection codes

| Code | Meaning |
|------|---------|
| `lookahead_published_at` | Atom not yet public at `as_of` |
| `lookahead_simulation_time` | Event time beyond horizon |
| `forbidden_post_hoc_source` | Retrospective / next-day label |
| `future_price_leak` | Uses future price explicitly |
| `published_after_event_time` | `published_at > time` (labeling error) |

## Available cases

| Case ID | Event | Date |
|---------|-------|------|
| `nflx_2022q1_earnings` | NFLX Q1 subscriber miss + guidance cut | 2022-04-19 |
| `snap_2022q3_earnings` | SNAP Q3 ad revenue miss | 2022-10-20 |
| `meta_2022q4_earnings` | META DAU decline + weak Q1 guidance | 2022-02-02 |
| `shop_2022q2_earnings` | SHOP e-commerce slowdown + guidance cut | 2022-07-26 |
| `hindenburg_nikola_2020` | Hindenburg short report on NKLA | 2020-09-10 |
| `gme_2021_01_squeeze` | GME Reddit short squeeze (+44% session) | 2021-01-27 |
| `luckin_2020_fraud` | Muddy Waters Luckin fraud report | 2020-01-31 |
| `fomc_2022_75bp` | FOMC 75bp hike + hawkish dots | 2022-09-21 |
| `cpi_2022_06_hot` | June 2022 CPI 9.1% hot print | 2022-07-13 |

## Atom extraction pipeline

Place raw sources under `sources/` and run extraction to produce `atoms.jsonl`:

```
data/market/case_studies/<case_id>/
  manifest.json
  scenario.json
  sources/
    sources.json       # document manifest + atom_id_prefix
    sec_8k.txt         # or short_report.txt, fomc_statement.txt, …
    earnings_call.txt
    news.jsonl         # {"published_offset_min", "headline", "source_type", …}
  atoms.jsonl          # generated
  extraction_report.json
```

```bash
# One case
python -m market_causal_engine.main --extract-atoms meta_2022q4_earnings

# All cases with sources/
python -m market_causal_engine.main --extract-all
python scripts/build_all_cases.py

# Then replay
python -m market_causal_engine.main --case-study meta_2022q4_earnings --as-of 120
```

Extraction uses regex rules in `market_causal_engine/extraction/patterns.py`, then the existing compiler maps tags/keywords to kernel events. Post-hoc headlines (e.g. `source_class: calibration_label`) are extracted but rejected at replay by look-ahead policy.

### EDGAR auto-fetch

Cases with an `edgar` block in `sources/sources.json` can pull live 8-K text from SEC EDGAR:

```bash
# Fetch raw filing → sources/sec_8k_edgar.txt (does not overwrite curated sec_8k.txt)
python -m market_causal_engine.main --fetch-edgar nflx_2022q1_earnings
python -m market_causal_engine.main --fetch-edgar-all

# Fetch then extract + replay
python -m market_causal_engine.main --fetch-and-extract shop_2022q2_earnings --as-of 120
```

Set a compliant User-Agent for SEC (required):

```bash
export MARKET_CAUSAL_SEC_USER_AGENT="YourApp/1.0 (you@example.com)"
```

Curated `sec_8k.txt` summaries remain the default pipeline input when no EDGAR summary exists. When `sec_8k_edgar_summary.txt` is present (from `--fetch-edgar` or raw `sec_8k_edgar.txt`), extraction **automatically prefers the summary** for atom parsing.

### Macro auto-fetch (FOMC / BLS CPI)

Cases with a `macro_fetch` block in `sources/sources.json`:

```bash
python -m market_causal_engine.main --fetch-macro fomc_2022_75bp
python -m market_causal_engine.main --fetch-macro-all
python -m market_causal_engine.main --fetch-and-extract-macro cpi_2022_06_hot --as-of 90
```

```json
"macro_fetch": {
  "source": "fomc",
  "event_date": "2022-09-21",
  "output": "fomc_statement.txt"
}
```

CPI example uses `"source": "bls_cpi"` with `"release_date"` and optional `"period"`.

## Commands

```bash
# List cases
python -m market_causal_engine.main --list-case-studies

# Look-ahead audit only
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --validate-lookahead --as-of 120

# Full replay (AH + earnings call window, 120 min)
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --as-of 120 --explain

# Counterfactual: no downgrade / company clarification / no gamma
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --case-counterfactual --as-of 120

# W1 vs W0 on historical feed
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --world W1 --diff-against W0 --as-of 120 --explain
```

## Output fields

- `lookahead_audit` — accepted/rejected atoms with reason codes
- `case_study` — observed vs simulated qualitative alignment
- `mvp_output` — earnings impact path + mechanism contributions
- `mechanism_contributions` — fundamental / sentiment / liquidity shares

## Adding a new case

1. Create `data/market/case_studies/<case_id>/manifest.json`
2. Add `scenario.json` (initial state only, no triggers)
3. Add `sources/sources.json` + raw SEC/news documents, then run `--extract-atoms <case_id>`
   - Or hand-author `atoms.jsonl` with timestamped public evidence
4. Include trap atoms (next-day / calibration) to verify look-ahead rejects them
5. Document `observed_outcomes` from public sources — **never** pass returns into kernel
6. Add calibration anchor in `data/market/calibration/impact_anchors.json` if needed

## Disclaimer

Case studies demonstrate **event forensics** on stylized public timelines. They are not backtests and do not claim predictive accuracy.
