# Benchmark Report — `benchmark_20260609_034558_0a82cbde`

Generated: 2026-06-09T03:45:59+00:00

## Summary

| Metric | Value |
|--------|-------|
| Events replayed | 113 |
| Direction accuracy (overall) | 0.600 |
| OOT train accuracy | 0.711 |
| OOT test accuracy | 0.182 |
| Mean cal error (real cases) | 1.2% |
| Placebo false-positive rate | 0.000 |

## By corpus

- **earnings_sp500_2016_2025**: n=50 dir_acc=0.200 placebo_fp=None
- **short_reports_public**: n=6 dir_acc=1.000 placebo_fp=None
- **macro_releases**: n=6 dir_acc=0.500 placebo_fp=None
- **company_shocks**: n=3 dir_acc=None placebo_fp=None
- **placebo_quiet_days**: n=48 dir_acc=1.000 placebo_fp=0.000

## Ablation (case studies)

- `no_news`: flip_rate=0.200 path_changes=1
- `no_sec`: flip_rate=0.200 path_changes=4
- `no_price`: flip_rate=0.000 path_changes=1

## Notes

- Catalog earnings use **synthetic proxy labels** for scale testing; full case studies use real observed outcomes.
- Target: placebo FP rate < 5%; document actual above.
- This report is for model validation / governance, not investment advice.
