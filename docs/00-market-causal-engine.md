# Market Event Causal Engine

**Trace-first causal runtime for compiling financial text and market signals into auditable event-impact pathways.**

## 产品定位

可解释的市场事件因果推演系统 — 三条引擎产品线：

| 引擎 | 场景 / Case | 核心输出 |
|------|-------------|----------|
| **Earnings** | E1/E2 + NFLX/SNAP/META/SHOP case | 冲击路径 · 机制贡献 · 校准后收益估计 |
| **Short Report** | S1/S2 + Hindenburg/NKLA case | 信任路径 · 监管风险 · 反转/延续 |
| **Macro** | X1/X2 + FOMC/CPI case | macro→sector→stock 传导 |

## 全量能力

- **Outcome 阻尼**：多层事件叠加不再饱和到 1.0
- **路径加权归因**：fundamental / sentiment / liquidity 按主导因果链加权
- **Post-hoc 校准**：`calibrated_impact` 映射 AH 跌幅（不进 kernel，无 look-ahead）
- **Case 级干预**：每个历史 case 可覆盖 W0–W7 时间与参数（如 NFLX W3 @ t=62）
- **Look-ahead 校验**：`published_at` + post-hoc source 拒绝

## 历史 Case Study

```bash
python -m market_causal_engine.main --list-case-studies
python -m market_causal_engine.main --extract-all          # SEC/news → atoms.jsonl
python -m market_causal_engine.main --fetch-edgar nflx_2022q1_earnings
python -m market_causal_engine.main --fetch-macro fomc_2022_75bp
python -m market_causal_engine.main --case-study shop_2022q2_earnings --as-of 120 --explain
python -m market_causal_engine.main --case-study nflx_2022q1_earnings --case-counterfactual --as-of 120
```

详见 [case-study-methodology.md](case-study-methodology.md)

## 快速开始（合成场景）

```bash
python -m market_causal_engine.main --list-domains
python -m market_causal_engine.main --scenario-id E1 --world W0 --explain
python -m market_causal_engine.main --scenario-id S1 --feed data/market/atoms/S1_feed.jsonl
python -m market_causal_engine.main --scenario-id X1 --counterfactual-suite
```

## 测试

```bash
pytest tests/ -v   # 143 tests
```

## 免责声明

用于 explainability / event forensics，不承诺 alpha。
