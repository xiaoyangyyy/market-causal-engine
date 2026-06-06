# Market Event Causal Engine

Trace-first **market event causal forensics** — compiles SEC filings, news, and market signals into auditable impact pathways. **Not a buy/sell predictor.**

Three product lines:

| Line | Scenarios | Focus |
|------|-----------|-------|
| **Earnings** | E1, E2 | 财报冲击路径 · 基本面/情绪/流动性贡献 · 9 历史 case |
| **Short Report** | S1, S2 | 做空报告 · 信任/流动性 · squeeze & fraud cases |
| **Macro** | X1, X2 | FOMC/CPI → sector → stock 传导 |

## Quick start

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
python -m pytest tests/ -q   # 143 tests
```

## Project structure

```
market_causal_engine/     # Kernel, mechanisms, extraction, case studies
data/market/              # Scenarios, case studies, compiler rules, calibration
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
