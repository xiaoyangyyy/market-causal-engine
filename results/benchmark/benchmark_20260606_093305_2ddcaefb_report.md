# Benchmark Report — `benchmark_20260606_093305_2ddcaefb`

Generated: 2026-06-06T09:33:05+00:00

## Summary

| Metric | Value |
|--------|-------|
| Events replayed | 48 |
| Direction accuracy (overall) | 1.000 |
| OOT train accuracy | 1.000 |
| OOT test accuracy | None |
| Mean cal error (real cases) | None |
| Placebo false-positive rate | 0.000 |

## By corpus

- **placebo_quiet_days**: n=48 dir_acc=1.000 placebo_fp=0.000

## Ablation (case studies)

- `no_news`: flip_rate=0.000 path_changes=0
- `no_sec`: flip_rate=0.000 path_changes=4
- `no_price`: flip_rate=0.000 path_changes=0

## Notes

- Catalog earnings use **synthetic proxy labels** for scale testing; full case studies use real observed outcomes.
- Target: placebo FP rate < 5%; document actual above.
- This report is for model validation / governance, not investment advice.
