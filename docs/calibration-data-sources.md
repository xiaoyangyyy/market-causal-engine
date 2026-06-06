# Phase 8 真实世界校准数据来源

## 原则
- 仅用于**事后校准**与一致性检查，不做“预测未来结果”。
- 公开报道与聚合指标映射为 `[0,1]` 风险代理值，不是真实概率。
- **不要**把 API key 写入仓库；GDELT DOC API 无需 key。

## 场景映射（Qatar 2022 代理）

| 引擎场景 | 真实代理事件 | 来源 |
|----------|--------------|------|
| S1 争议判罚 | 日本 2-1 西班牙 VAR 进球争议（2022-12-01） | [BBC Sport](https://www.bbc.co.uk/sport/football/63832775) |
| S2 出局散场 | 巴西被淘汰 + 赛后聚集（无重大治安事件） | [Peninsula Qatar / MoI](https://thepeninsulaqatar.com/article/07/12/2022/no-major-security-incident-recorded-the-safest-fifa-world-cup-so-far-says-security-authorities) |
| S3 高温人群 | 开幕前 Fan Zone 拥堵（2022-11-19/20） | [NBC News](https://www.nbcnews.com/news/us-news/day-fifa-world-cup-qatar-faces-overcrowding-troubles-rcna58033) |

## 线上舆情（可选增强）
- **GDELT DOC 2.0** `timelinevolraw`：查询 `Japan Spain VAR World Cup`、`Qatar World Cup fan zone`
- 缓存路径：`data/calibration_raw/gdelt_*.json`
- 若 429 限流，使用 `qatar_wc2022_public_facts.json` 中的手工归一化值

## 一键下载 + 校准

```powershell
cd e:\ca
python scripts/fetch_and_calibrate.py --scenarios S1,S2,S3 --budget 120
python scripts/merge_calibrated_priors.py
```

输出：
- `data/observations/real_qatar2022_S*_w0.jsonl`
- `results/calibration/*_calibration_report.json|md`
- `results/calibration/real_world_calibration_summary.json`
- **`data/priors/mechanisms_v0.2_calibrated.json`**（合并后的默认可用先验）

## 使用校准先验跑场景

```powershell
# 全局合并校准（三场景加权平均）
python -m worldcup_causal_engine.main --scenario data/scenarios/S3_heat_crowd_comm_delay.json --priors-profile calibrated --explain

# 场景专属校准（更贴近该场景真实代理）
python -m worldcup_causal_engine.main --scenario data/scenarios/S1_controversial_call_high_density.json --priors-profile calibrated --scenario-specific-priors --explain
```

## Observation JSONL 格式

```json
{"scenario_id":"S1_controversial_call_high_density","world_id":"W0","time_bucket":"final","key":"verbal_conflict","value":0.08,"weight":2.0,"meta":{"fact_id":"japan_spain_var_dec2022","source":"BBC Sport / FIFA post-hoc VAR release","url":"https://www.bbc.co.uk/sport/football/63832775"}}
```

## 字段含义

| key | 含义 | 引擎对齐字段 |
|-----|------|--------------|
| verbal_conflict | 言语冲突风险代理 | `final_risk.verbal_conflict` |
| scuffle / riot / panic | 肢体/骚乱/恐慌代理 | `final_risk.*` |
| rumor_volume_index | 舆情强度代理 | `final_state.rumor_volume` |

