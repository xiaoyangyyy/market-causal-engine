# Benchmark Report — `benchmark_20260606_092444`

Generated: 2026-06-06T09:24:45+00:00

## Summary

| Metric | Value |
|--------|-------|
| Events replayed | 40 |
| Direction accuracy (overall) | 0.325 |
| OOT train accuracy | 0.25 |
| OOT test accuracy | 1.0 |
| Mean cal error (real cases) | 2.1% |
| Placebo false-positive rate | None |

## By corpus

- **earnings_sp500_2016_2025**: n=40 dir_acc=0.325

## Ablation (case studies)

- `no_news`: flip_rate=0.0 path_changes=0
- `no_sec`: flip_rate=0.0 path_changes=4
- `no_price`: flip_rate=0.0 path_changes=0

## Notes

- Catalog earnings use **synthetic proxy labels** for scale testing; full case studies use real observed outcomes.
- Target: placebo FP rate < 5%; document actual above.
- This report is for model validation / governance, not investment advice.
