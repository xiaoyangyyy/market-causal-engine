# Phase 2：逆向调试与干预实验

**阶段目标**：实现 Reverse Debugger 完整 API，扩展主链路 B/C，完成 S1–S3 场景 × W0–W5 多世界压力测试与干预对比。  
**预计工期**：1–2 周  
**前置依赖**：[Phase 1：核心引擎与主链路](./phase-01-核心引擎与主链路.md)  
**后续阶段**：[Phase 3：文本证据层](./phase-03-文本证据层.md)

---

## 1. 阶段交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 逆向调试器 | `worldcup_causal_engine/reverse.py` | 路径分析、阻断解释、多世界 diff |
| 实验框架 | `worldcup_causal_engine/experiments.py` | 批量跑场景、汇总指标 |
| 城市机制 | `mechanisms/city.py` | 交通、高温、fan zone |
| 安保机制 | `mechanisms/security.py` | 警力、信任、降级 |
| 扩展干预 | `mechanisms/intervention.py` | W2–W5 全部干预 |
| 场景 S2/S3 | `data/scenarios/` | 出局+交通、高温+拥挤 |
| 干预配置 | `data/interventions/` | W0–W5 JSON |
| 测试 | `tests/test_reverse.py`, `tests/test_experiments.py` | |
| 实验报告 | `results/experiment_1/` | 批量 JSON + 汇总表 |

---

## 2. 任务清单

### 2.1 Reverse Debugger (`reverse.py`)

#### 2.1.1 输入

- Kernel run 产出的 `trace: list[TraceEntry]`
- `MECHANISM_INDEX` 用于查 spec

#### 2.1.2 核心函数

| 函数 | 任务 | 完成标准 |
|------|------|----------|
| `trace_path(event_id)` | 从 event 沿 cause 回溯到根 | 返回有序 kind 列表 |
| `why_blocked(event_id)` | 查 blocked trace entry | 返回 flags/resources 原因 |
| `why_not_happen(kind)` | 扫描 trace 找同类 block 或缺失 | 返回原因分类 |
| `resource_bottlenecks()` | 聚合 resource_shortage | 返回 `{resource, failures}` 排序 |
| `flag_lifecycle(flag)` | 扫描 set/clear 记录 | 返回 `[(time, action)]` |
| `variable_history(variable)` | 从 commit patch 重建序列 | 返回 `[(time, value)]` |
| `dominant_risk_path()` | 找导致风险变量最大增幅的事件链 | 返回 kind 列表 |
| `diff_trace(run_a, run_b)` | 两 trace 路径对称差分 | 返回 fork_point, only_a, only_b |

- [ ] 实现上述 8 个函数
- [ ] 提供 `ReverseDebugger(trace, final_state, mechanism_index)` 类封装
- [ ] 输出人类可读 `explain()` 文本（供 CLI `--explain`）

#### 2.1.3 dominant_risk_path 算法（v0.1）

1. 找 `verbal_conflict_risk` / `scuffle_risk` / `riot_risk` / `panic_risk` 增幅最大的 trace entry
2. 从该 entry 的 event_id 回溯 cause 链
3. 过滤 status=executed 的节点
4. 去重相邻重复 kind

### 2.2 扩展机制：主链路 B

| kind | 文件 | 触发 | 效果 |
|------|------|------|------|
| `team_eliminated` | match.py | S2 trigger | humiliation_level↑, TEAM_ELIMINATED |
| `fans_gather` | crowd.py | TEAM_ELIMINATED / match_end | crowd_density↑, fan_zone_pressure↑ |
| `bar_district_pressure` | crowd.py | fans_gather + 高密度 | 升 scuffle_risk 基底 |

- [ ] 链路 B 机制实现
- [ ] S2 场景 JSON
- [ ] 链路 B 集成测试

### 2.3 扩展机制：主链路 C

| kind | 文件 | 触发 | 效果 |
|------|------|------|------|
| `match_end` | match.py | 场景 trigger t=90 | emit fans_gather |
| `transit_delay` | city.py | match_end + 高 transit_pressure | TRANSIT_DELAY_ACTIVE |
| `crowd_density_spike` | crowd.py | TRANSIT_DELAY_ACTIVE | CROWD_DENSITY_HIGH |
| `queue_overflow` | crowd.py | CROWD_DENSITY_HIGH + fan_zone 满 | fan_zone_pressure↑ |
| `crowd_push` | crowd.py | queue_overflow | panic_risk↑ |
| `panic_signal` | crowd.py | crowd_push | panic_risk 大幅↑ |

- [ ] 城市机制 `city.py`
- [ ] 链路 C 机制实现
- [ ] S3 场景 JSON（高温 + 拥挤 + 沟通延迟）

### 2.4 完整干预方案 W0–W5

| 世界 | kind | 时间 | 资源 | 效果 |
|------|------|------|------|------|
| W0 | — | — | — | 基线 |
| W1 | official_clarification | t=75 | official_comm_channel:1 | rumor↓, clear RUMOR_SPIKE |
| W2 | team_captain_message | t=72 | — | outrage_frame↓ |
| W3 | separate_fan_flows | t=80 | police_units:5 | 阻止 OPPOSING_FANS_COLOCATED |
| W4 | transit_reroute | t=90 | transport_capacity:200 | transit_pressure↓ |
| W5 | deploy_deescalation | t=78 | deescalation_teams:3 | deescalation_capacity↑, verbal_risk↓ |

- [ ] 每个干预写独立 JSON：`data/interventions/W1.json` … `W5.json`
- [ ] `scenarios.py` 支持 `--world` 加载干预序列
- [ ] 干预失败路径进入 trace + reverse 可解释

### 2.5 实验框架 (`experiments.py`)

```python
def run_pressure_test(scenarios, worlds, until=120) -> list[RunResult]: ...
def summarize(results) -> pd.DataFrame | dict: ...
def find_best_cut_points(base_run, intervention_runs) -> list[CutPoint]: ...
def export_report(results, path): ...
```

- [ ] 批量运行 S1–S3 × W0–W5（共 18 runs）
- [ ] 每次运行保存完整 JSON 到 `results/experiment_1/{scenario}_{world}.json`
- [ ] 生成汇总表：scenario, world, final_risk, dominant_path, bottlenecks
- [ ] `find_best_cut_points`：比较 W0 vs Wk，找第一个分叉事件前的可干预点

### 2.6 CLI 扩展

```bash
# 单 run 带解释
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W1 --until 120 --explain

# 批量实验
python -m worldcup_causal_engine.experiments \
  --experiment pressure_test \
  --scenarios S1,S2,S3 \
  --worlds W0,W1,W2,W3,W4,W5 \
  --output results/experiment_1/
```

- [ ] `--explain` 调用 reverse.debugger 输出 dominant_path + bottlenecks
- [ ] `experiments` 子命令或独立模块入口

---

## 3. 场景定义

### S1：争议判罚 + 高密度 fan zone（Phase 1 已有，本阶段补全 W2–W5 测试）

```json
{
  "scenario_id": "S1_controversial_call_high_density",
  "trigger": { "kind": "controversial_call", "time": 70, "severity": 0.8 },
  "context": {
    "crowd_density": 0.75,
    "media_attention": 0.6,
    "police_trust": 0.45,
    "rivalry_intensity": 0.7
  }
}
```

### S2：主队出局 + 交通延误

```json
{
  "scenario_id": "S2_team_eliminated_transit_delay",
  "triggers": [
    { "kind": "team_eliminated", "time": 88, "severity": 0.9 },
    { "kind": "transit_delay", "time": 95, "severity": 0.7 }
  ],
  "context": {
    "crowd_density": 0.65,
    "transit_pressure": 0.7,
    "humiliation_level": 0.2,
    "police_trust": 0.5
  }
}
```

### S3：高温 + 拥挤 + 官方沟通延迟

```json
{
  "scenario_id": "S3_heat_crowd_comm_delay",
  "triggers": [
    { "kind": "controversial_call", "time": 55, "severity": 0.6 },
    { "kind": "match_end", "time": 90, "severity": 1.0 }
  ],
  "context": {
    "heat_stress": 0.85,
    "crowd_density": 0.8,
    "fan_zone_pressure": 0.75,
    "police_trust": 0.4
  },
  "resources_override": {
    "official_comm_channel": 0
  }
}
```

---

## 4. 测试用例

### 4.1 Reverse 单测

- [ ] `trace_path` 对已知链返回正确顺序
- [ ] `why_blocked` 解析 missing_flags 与 resource_shortage
- [ ] `diff_trace` 识别 fork_point（如 W1 在 official_clarification 处分叉）
- [ ] `dominant_risk_path` 与手工标注一致

### 4.2 实验集成

- [ ] `run_pressure_test` 18 runs 无异常
- [ ] S3 + W0 产生 official_comm_channel bottleneck
- [ ] S1 + W3 的 OPPOSING_FANS_COLOCATED 可不成立

---

## 5. 验收标准（Phase 2 Done）

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 8 个 reverse API 全部可用 | 单测 + CLI --explain |
| 2 | S1–S3 场景均可跑通 | 集成测试 |
| 3 | W0–W5 干预均可注入 | 18-run 实验 |
| 4 | `diff_trace(W0, W1)` 有明确分叉点 | 人工检查 S1 输出 |
| 5 | `best_cut_points` 对 S1 至少输出 2 条建议 | 汇总 JSON |
| 6 | 实验报告 JSON + 汇总表产出 | `results/experiment_1/summary.json` |

---

## 6. 实验 1 输出模板

`results/experiment_1/summary.json`：

```json
{
  "experiment": "pressure_test",
  "runs": 18,
  "results": [
    {
      "scenario_id": "S1_controversial_call_high_density",
      "world_id": "W0",
      "final_risk": { "verbal_conflict": 0.68, "scuffle": 0.47 },
      "dominant_path": ["controversial_call", "media_blame_frame", "..."],
      "resource_bottlenecks": [{ "resource": "official_comm_channel", "failures": 0 }],
      "best_cut_points": []
    }
  ],
  "cross_scenario_insights": {
    "most_effective_intervention": "W1",
    "most_common_bottleneck": "official_comm_channel"
  }
}
```

---

## 7. 本阶段不做

- Atom/Compiler 文本管道（Phase 3）
- 消融实验（Phase 4）
- LLM baseline 对比（Phase 4）
- 可视化前端（可选放到 Phase 4）

---

## 8. 建议实施日程

| 天 | 任务 |
|----|------|
| D1–D2 | reverse.py 全 API |
| D3 | 链路 B + S2 |
| D4 | 链路 C + city.py + S3 |
| D5 | W2–W5 干预机制 |
| D6 | experiments.py 批量跑 |
| D7 | 测试、汇总报告、调参 |

---

*完成 Phase 2 后进入 [Phase 3](./phase-03-文本证据层.md)。*
