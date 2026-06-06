# Phase 7–8 + 长期能力（Priority C）

## Phase 7：事件级 MDG + 证据类型

- **MDG**：`worldcup_causal_engine/mdg/` — 从 contract / spec / trace 构建事件依赖图
- **导出**：JSON（`--mdg`）、Mermaid（`--mdg-mermaid-output` 或 `scripts/export_mdg.py`）
- **Typed evidence**：`evidence_types.py` — Atom/CompiledEvent 带 `evidence_type`

```powershell
python -m worldcup_causal_engine.main --scenario data/scenarios/S1_controversial_call_high_density.json --world W0 --mdg --mdg-mermaid-output paper/figures/mdg/S1.mmd
python scripts/export_mdg.py
```

## Phase 8：事后校准

- **观测**：`data/observations/real_qatar2022_*.jsonl`
- **校准先验**：`data/priors/mechanisms_v0.2_calibrated.json`
- **一键**：`python scripts/fetch_and_calibrate.py`

```powershell
python -m worldcup_causal_engine.main --scenario data/scenarios/S3_heat_crowd_comm_delay.json --priors-profile calibrated --scenario-specific-priors
```

## Priority C

### LLM 提案（仅提案，Kernel 验证）

```powershell
# Mock（无 API key）
python -m worldcup_causal_engine.main --scenario data/scenarios/S3_heat_crowd_comm_delay.json --llm-propose-demo

# 真实 API（见 .env.example）
$env:ZHISUAN_API_KEY="sk-..."
python -m worldcup_causal_engine.main --scenario data/scenarios/S1_controversial_call_high_density.json --llm-propose-demo --use-api --model qwen3.5 --base-url https://ai.azya.top/v1
```

### 新场景 S4–S6 + W6

| ID | 文件 | 要点 |
|----|------|------|
| S4 | `S4_misleading_viral_clip.json` | 高 misinfo + 争议判罚 → 谣言链 |
| S5 | `S5_post_match_transit_delay.json` | 赛后散场 + 交通容量不足 |
| S6 | `S6_heat_fanzone_overflow.json` | 高温 + fan zone 容量枯竭 |
| W6 | `W6.json` | `platform_rumor_throttle`（消耗 fact_check_capacity） |

```powershell
python -m worldcup_causal_engine.main --scenario data/scenarios/S4_misleading_viral_clip.json --world W6 --diff-against W0 --explain
```
