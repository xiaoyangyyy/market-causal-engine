# Benchmark Report — `benchmark_20260606_093136_33d7ef7e`

Generated: 2026-06-06T09:31:36+00:00

## Summary

| Metric | Value |
|--------|-------|
| Events replayed | 10 |
| Direction accuracy (overall) | 0.875 |
| OOT train accuracy | 1.000 |
| OOT test accuracy | 0.000 |
| Mean cal error (real cases) | 0.2% |
| Placebo false-positive rate | 0.000 |

## By corpus

- **placebo_quiet_days**: n=5 dir_acc=1.000 placebo_fp=0.000
- **macro_releases**: n=5 dir_acc=0.667 placebo_fp=None

## Notes

- Catalog earnings use **synthetic proxy labels** for scale testing; full case studies use real observed outcomes.
- Target: placebo FP rate < 5%; document actual above.
- This report is for model validation / governance, not investment advice.
