# Benchmark Report — `benchmark_20260615_123914_9af8d5cd`

Generated: 2026-06-15T12:39:21+00:00

## Headline metrics (real-label only)

_Use these for README / external reporting. Do not cite mixed overall accuracy._

| Metric | Value |
|--------|-------|
| Real-label events | 108 |
| Real-label direction accuracy | 1.000 |
| Placebo false-positive rate | 0.000 |
| **Catalog-only EDGAR path** | 0.591 (n=920) |
| OOT test (real-label, post-2022-01-01) | 1.000 |

### By corpus (real-label subset)

- **earnings_sp500_2016_2025**: n=100 dir_acc=1.000
- **short_reports_public**: n=3 dir_acc=None
- **macro_releases**: n=2 dir_acc=None
- **company_shocks**: n=3 dir_acc=None

### Naive baselines (real-label)

- Always-neutral accuracy: 0.560
- Always-majority (neutral): 0.560
- Class distribution: `{'neutral': 56, 'down': 18, 'up': 26}`

### Router path split (real-label earnings)

- Catalog path: n=0 acc=None
- Scenario router path: n=108 acc=1.000

## Appendix — mixed / legacy (not headline)

| Metric | Value |
|--------|-------|
| Mixed overall direction accuracy | 0.987 |
| Proxy-label events in run | 7 |
| Legacy summary count | 163 |

_Inflated when earnings router defaults to scenario templates (E1/E2). Use headline.real_label_* and catalog_only instead._


## Notes

- **Catalog-only** = quality-filtered EDGAR atoms + LLM claims, no scenario router.
- **Real-label** = Yahoo daily or case-study observed outcomes; proxy labels excluded from headline.
- Target: placebo FP rate < 5%; document actual above.
- This report is for model validation / governance, not investment advice.
