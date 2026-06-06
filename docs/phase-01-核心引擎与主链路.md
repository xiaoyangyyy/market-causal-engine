# Phase 1：核心引擎与主链路 A

**阶段目标**：搭建可运行的运行时因果 Kernel，跑通争议判罚主链路（链路 A），支持 S1 场景 W0/W1 对比。  
**预计工期**：1–2 周  
**前置依赖**：无  
**后续阶段**：[Phase 2：逆向调试与干预实验](./phase-02-逆向调试与干预实验.md)

---

## 1. 阶段交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| Kernel 核心 | `worldcup_causal_engine/kernel.py` | 调度、state、flags、resources、trace |
| 机制注册 | `worldcup_causal_engine/registry.py` | `@mechanism` + `MECHANISM_INDEX` |
| 比赛机制 | `worldcup_causal_engine/mechanisms/match.py` | `controversial_call` 等 |
| 媒体机制 | `worldcup_causal_engine/mechanisms/media.py` | `media_blame_frame`, `viral_clip_published` |
| 社交机制 | `worldcup_causal_engine/mechanisms/social.py` | `rumor_amplified` |
| 人群机制 | `worldcup_causal_engine/mechanisms/crowd.py` | `offline_mood_shift`, `opposing_fans_contact`, `verbal_conflict` |
| 干预机制 | `worldcup_causal_engine/mechanisms/intervention.py` | `official_clarification` |
| 场景配置 | `worldcup_causal_engine/scenarios.py` + `data/scenarios/` | S1 加载 |
| CLI 入口 | `worldcup_causal_engine/main.py` | 单次运行 + JSON 输出 |
| 单元测试 | `tests/test_kernel.py`, `tests/test_mechanisms.py` | 核心逻辑覆盖 |

---

## 2. 任务清单

### 2.1 项目初始化

- [ ] 创建 `worldcup_causal_engine/` 目录结构
- [ ] 添加 `pyproject.toml` 或 `requirements.txt`（Python 3.10+）
- [ ] 定义 `State`、`Resources`、`Flags` 常量模块或 `scenarios.py` 内枚举
- [ ] 建立 `data/scenarios/S1_controversial_call_high_density.json`
- [ ] 建立 `data/priors/mechanisms_v0.1.json`（机制参数中值）

### 2.2 Kernel 实现 (`kernel.py`)

#### 2.2.1 数据结构

- [ ] `Event`：id, kind, time, priority, payload, cause, status
- [ ] `TraceEntry`：event_id, kind, time, action, patch, flags_delta, resource_delta, cause, blocked_reason
- [ ] `KernelState`：state dict, flags set, resources dict, trace list, event_counter

#### 2.2.2 事件队列

- [ ] 按 `(time, priority, seq)` 排序的优先队列
- [ ] `emit()`：创建事件并入队，记录 cause
- [ ] `do()`：干预专用 emit，默认 priority=0

#### 2.2.3 状态操作

- [ ] `commit(event, patch)`：合并 patch 到 state，clamp 到 [0, 1]（风险变量）
- [ ] `set_flag(flag, cause)` / `clear_flag(flag, cause)`
- [ ] `has_flags(*flags)`：检查全部存在

#### 2.2.4 资源操作

- [ ] `acquire(resource, amount, cause)` → bool
- [ ] `release(resource, amount, cause)`
- [ ] 失败时写 trace，`blocked_reason="resource_shortage:{resource}"`

#### 2.2.5 主循环

- [ ] `run(until)`：弹出到期事件，查 registry 调机制 handler
- [ ] 机制内 `waits` 不满足 → trace 记录 `blocked_reason="missing_flags:..."`，跳过执行
- [ ] 每个成功执行的机制写完整 trace entry

#### 2.2.6 运行结果导出

- [ ] `to_result()` → 包含 final_state, final_risk, trace, active_flags

### 2.3 Registry 实现 (`registry.py`)

- [ ] `@mechanism(...)` 装饰器，注册 handler + spec
- [ ] `MECHANISM_INDEX: dict[str, MechanismSpec]`
- [ ] `get_handler(kind)` / `get_spec(kind)` 查询接口
- [ ] 启动时 `import mechanisms.*` 触发注册

### 2.4 机制实现（主链路 A）

按实施顺序逐个实现并单测：

| 顺序 | kind | 文件 | waits | resources | 说明 |
|------|------|------|-------|-----------|------|
| 1 | `controversial_call` | match.py | — | — | 场景触发器注入；升 perceived_unfairness, match_tension；设 CONTROVERSIAL_CALL_VISIBLE |
| 2 | `viral_clip_published` | media.py | CONTROVERSIAL_CALL_VISIBLE | media_attention_budget:1 | 升 platform_velocity |
| 3 | `media_blame_frame` | media.py | CONTROVERSIAL_CALL_VISIBLE | — | 升 outrage_frame, blame_frame；设 MEDIA_OUTRAGE_FRAME_ACTIVE |
| 4 | `rumor_amplified` | social.py | MEDIA_OUTRAGE_FRAME_ACTIVE | media_attention_budget:2 | 升 rumor_volume, misinfo_confidence；rumor_volume>0.6 设 RUMOR_SPIKE |
| 5 | `offline_mood_shift` | crowd.py | RUMOR_SPIKE | — | 升 verbal_conflict_risk 基底 |
| 6 | `opposing_fans_contact` | crowd.py | — | — | 需 crowd_density>0.5 或 RUMOR_SPIKE；设 OPPOSING_FANS_COLOCATED |
| 7 | `verbal_conflict` | crowd.py | OPPOSING_FANS_COLOCATED | — | 升 verbal_conflict_risk, scuffle_risk |

### 2.5 干预机制（W1）

- [ ] `official_clarification`（intervention.py）
  - priority=0，由 `do()` 在 t=75 注入
  - 需要 `official_comm_channel: 1`
  - 成功：rumor_volume -= 0.25，clear RUMOR_SPIKE
  - 失败：trace 记录资源瓶颈

### 2.6 场景加载 (`scenarios.py`)

- [ ] `load_scenario(path)` → initial_state, resources, trigger, context
- [ ] `apply_context(kernel, context)`：覆盖初始 state
- [ ] `inject_trigger(kernel, trigger)`：在 trigger.time emit controversial_call
- [ ] `load_intervention(path)` → intervention event list

### 2.7 CLI (`main.py`)

```bash
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W0 \
  --until 120 \
  --output results/S1_W0.json
```

- [ ] 支持 `--world W0|W1`
- [ ] 输出 JSON 到 stdout 或文件
- [ ] 打印简要 dominant_path（Phase 1 可先用 trace 顺序近似）

---

## 3. 机制参数（v0.1 中值）

```json
{
  "controversial_call": {
    "unfairness_delta": 0.35,
    "tension_delta": 0.25,
    "emit_viral_clip_delay": 3
  },
  "viral_clip_published": {
    "platform_velocity_delta": 0.3,
    "emit_blame_frame_delay": 5
  },
  "media_blame_frame": {
    "outrage_delta": 0.3,
    "blame_delta": 0.2,
    "emit_rumor_delay": 8
  },
  "rumor_amplified": {
    "rumor_delta": 0.35,
    "misinfo_delta": 0.2,
    "rumor_spike_threshold": 0.6,
    "emit_mood_shift_delay": 5
  },
  "offline_mood_shift": {
    "verbal_risk_delta": 0.15,
    "emit_contact_delay": 10
  },
  "opposing_fans_contact": {
    "colocation_threshold_crowd": 0.5,
    "emit_conflict_delay": 5
  },
  "verbal_conflict": {
    "verbal_risk_delta": 0.25,
    "scuffle_risk_delta": 0.15
  },
  "official_clarification": {
    "rumor_reduction": 0.25,
    "credibility_multiplier": 0.7
  }
}
```

---

## 4. 测试用例

### 4.1 Kernel 单测

- [ ] emit 事件按 time+priority 正确排序
- [ ] acquire 失败不写 state patch
- [ ] set_flag / clear_flag 进入 trace
- [ ] 同场景两次 run 输出一致

### 4.2 机制单测

- [ ] `controversial_call` 触发后 CONTROVERSIAL_CALL_VISIBLE 为真
- [ ] 无 MEDIA_OUTRAGE_FRAME_ACTIVE 时 `rumor_amplified` 被 block
- [ ] `official_clarification` 资源为 0 时不降 rumor_volume

### 4.3 集成测试

- [ ] S1 + W0：verbal_conflict_risk > 0.5，trace 含完整链路
- [ ] S1 + W1（充足资源）：RUMOR_SPIKE 被清除，verbal_conflict_risk 低于 W0
- [ ] S1 + W1（official_comm_channel=0）：澄清失败，路径与 W0 相近

---

## 5. 验收标准（Phase 1 Done）

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | S1+W0 跑出完整 trace | 集成测试 + JSON artifact |
| 2 | dominant_path 含链路 A 核心节点 | 检查输出 JSON |
| 3 | W1 干预可改变风险或路径 | W0 vs W1 对比 |
| 4 | 资源不足可记录在 trace | official_comm_channel=0 测试 |
| 5 | 可复现 | 固定参数连跑 3 次 hash 一致 |

---

## 6. 本阶段不做

- Reverse Debugger 完整 API（Phase 2）
- 主链路 B/C（Phase 2）
- Atom / Claim Cluster / Compiler（Phase 3）
- 消融实验、LLM 对比（Phase 4）
- Web UI 或可视化大屏

---

## 7. 建议实施日程

| 天 | 任务 |
|----|------|
| D1 | 项目结构 + Kernel 队列 + state/flags |
| D2 | resources + trace + run loop |
| D3 | registry + match/media 机制 |
| D4 | social/crowd 机制 + 链路 A 联调 |
| D5 | intervention + scenarios + main.py |
| D6–D7 | 测试、调参、文档、S1 W0/W1 demo |

---

## 8. Phase 1 完成后的演示命令

```bash
# Baseline
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W0 --until 120 --output results/S1_W0.json

# Intervention
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W1 --until 120 --output results/S1_W1.json
```

预期：W1 的 `rumor_volume`、`verbal_conflict_risk` 低于 W0，或 dominant_path 在 `rumor_amplified` 前分叉。

---

*完成 Phase 1 后进入 [Phase 2](./phase-02-逆向调试与干预实验.md)。*
