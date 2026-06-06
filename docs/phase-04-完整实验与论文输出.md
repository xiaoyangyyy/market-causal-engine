# Phase 4：完整实验与论文输出

**阶段目标**：完成消融实验、LLM baseline 对比、敏感性分析，产出论文所需的图表、表格与可复现 artifact，回答 RQ1–RQ4。  
**预计工期**：2–3 周  
**前置依赖**：[Phase 3：文本证据层](./phase-03-文本证据层.md)

---

## 1. 阶段交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 消融实验 | `experiments.py --experiment ablation` | 6 组消融 |
| LLM 对比 | `experiments/llm_baseline.py` | 同等场景 JSON prompt |
| 敏感性分析 | `experiments/sensitivity.py` | 机制参数区间扫描 |
| 可视化脚本 | `scripts/plot_results.py` | 风险热图、路径图、diff 图 |
| 论文图表 | `paper/figures/`, `paper/tables/` | 可直接引用 |
| 复现包 | `results/reproducibility/` | 全部 JSON + config + hash |
| 实验报告 | `docs/experiment-report.md` | 完整结果叙述 |

---

## 2. 研究问题与实验映射

| RQ | 实验 | 主要指标 |
|----|------|----------|
| RQ1 | 实验 1 + Feed 模式 | dominant_path 完整性、链路覆盖率 |
| RQ2 | 实验 2 消融 + S3 瓶颈案例 | block 原因分布、flag/resource 贡献 |
| RQ3 | 实验 1 干预对比 + cut points | 风险差分、路径分叉、最优窗口 |
| RQ4 | 实验 3 LLM 对比 | 5 维可解释性评分 |

---

## 3. 实验 2：消融实验

### 3.1 消融维度

| 消融 ID | 移除组件 | 实现方式 |
|---------|----------|----------|
| A1 | without flags | 机制 ignores `waits`，全部放行 |
| A2 | without resources | `acquire` 永远成功 |
| A3 | without priority | 全部 priority=5，FIFO |
| A4 | without trace | 不记录 trace（反向对照） |
| A5 | without intervention | 只跑 W0 |
| A6 | without evidence ledger | 直接 inject compiled event，跳过 cluster |

- [ ] `KernelConfig` 支持消融开关
- [ ] 每个消融跑 S1–S3 × W0（9 runs）
- [ ] 完整系统跑 S1–S3 × W0（9 runs）作为对照

### 3.2 消融假设（论文表述）

| 消融 | 预期退化 |
|------|----------|
| A1 without flags | 路径异常增多，always-escalate，无法解释阻断 |
| A2 without resources | 干预永远“成功”，瓶颈消失，高估治理效果 |
| A3 without priority | 干预被延迟事件覆盖，cut point 窗口失真 |
| A4 without trace | 无法回答 why_blocked / diff_trace |
| A5 without intervention | 无法比较因果路径变化 |
| A6 without evidence ledger | 重复帖文重复触发，路径虚高 |

### 3.3 消融指标

```python
metrics = {
    "final_verbal_conflict_risk": float,
    "final_scuffle_risk": float,
    "path_length": int,
    "blocked_events_count": int,
    "unexplained_blocks": int,      # 无 trace 时 = N/A
    "always_escalate": bool,        # 风险单调不降
    "intervention_effect_visible": bool,
}
```

- [ ] `experiments.run_ablation()` 实现
- [ ] 输出 `results/experiment_2/ablation_summary.json`
- [ ] 生成对比表：完整系统 vs 各消融

---

## 4. 实验 3：LLM Baseline 对比

### 4.1 公平对比原则

- **相同输入**：scenario JSON + world 配置 + 机制先验摘要（不给 kernel 内部 trace）
- **相同输出维度**：final_risk, dominant_path, active_flags, bottlenecks, cut_points
- **多次运行**：LLM 跑 5 次测一致性；Kernel 跑 1 次（确定性）

### 4.2 LLM Prompt 模板

```
You are given a World Cup crowd-risk scenario in JSON.
Simulate the causal chain from the trigger event to offline risks.
Output STRICT JSON with fields:
  final_risk, dominant_path, active_flags,
  resource_bottlenecks, best_cut_points, reasoning

Scenario: {scenario_json}
Intervention: {world_json}
Mechanism priors (summary): {priors_summary}

Do not predict real-world outcomes. Reason only from given constraints.
```

- [ ] `llm_baseline.py`：支持 OpenAI / Anthropic / 本地模型接口
- [ ] 输出 JSON schema 校验
- [ ] 保存 5 次运行：`results/experiment_3/llm/{scenario}_{world}_run{i}.json`

### 4.3 五维可解释性评分

| 维度 | Kernel 评分方式 | LLM 评分方式 |
|------|-----------------|--------------|
| 可追踪性 | 每条路径有 trace entry = 1 | 有逐步 reasoning = 1，否则 0 |
| 一致性 | 单次确定性 = 1 | 5 次 path Jaccard 均值 |
| 未发生事件解释 | `why_not_happen` 可用 = 1 | 是否解释某事件未出现 |
| intervention diff | `diff_trace` 有分叉 = 1 | 输出是否区分 W0/W1 路径 |
| 资源瓶颈定位 | bottleneck 与 trace 一致 = 1 | 瓶颈是否匹配 scenario 资源 |

- [ ] `score_explainability(kernel_result, llm_results) -> dict`
- [ ] 输出雷达图数据 `paper/figures/explainability_radar.json`

### 4.4 案例研究（论文用）

选 2 个典型案例写深：

1. **S1 + W1**：Kernel 正确识别 official_comm_channel 瓶颈；LLM 是否忽略？
2. **S3 + W0**：高温+拥挤链；LLM 是否漏掉 transit → panic 中间节点？

- [ ] 每个案例一篇 `docs/case-study-{id}.md`（500–800 字）

---

## 5. 敏感性分析

### 5.1 扫描参数

对主链路 A 关键参数做网格/随机扫描：

| 参数 | 区间 |
|------|------|
| `rumor_amplified.rumor_delta` | [0.2, 0.5] |
| `media_blame_frame.outrage_delta` | [0.1, 0.4] |
| `official_clarification.rumor_reduction` | [0.1, 0.4] |
| `police_trust` 初始值 | [0.3, 0.7] |

- [ ] `sensitivity.py`：Latin hypercube 或 grid，每参数 5 点
- [ ] S1+W0 跑 100 次（或 grid 全组合）
- [ ] 输出：参数 → final_risk 散点/箱线图

### 5.2 论文用途

- 证明结论对参数区间**定性稳健**（路径结构不变，幅度变化）
- 回应“机制参数是手工设定”的审稿意见

---

## 6. 可视化与论文图表

### 6.1 必备图表

| 图号 | 内容 | 脚本 |
|------|------|------|
| Fig.1 | 系统架构图 | Mermaid / draw.io 导出 |
| Fig.2 | 主链路 A 机制图（带 flags/resources） | `plot_mechanism_graph.py` |
| Fig.3 | S1 W0 vs W1 diff_trace 分叉图 | `plot_diff_trace.py` |
| Fig.4 | 实验 1 风险热图（scenario × world） | `plot_risk_heatmap.py` |
| Fig.5 | 消融实验指标对比柱状图 | `plot_ablation.py` |
| Fig.6 | RQ4 五维雷达图（Kernel vs LLM） | `plot_explainability_radar.py` |
| Table.1 | 场景与干预配置表 | 手工 / CSV |
| Table.2 | 实验 1 汇总结果 | `summary.json` → LaTeX |
| Table.3 | 消融实验对比 | `ablation_summary.json` → LaTeX |
| Table.4 | LLM vs Kernel 评分 | `explainability_scores.json` → LaTeX |

- [ ] 所有图以 300dpi PNG + 矢量 PDF 导出
- [ ] 图注含 scenario/world 说明

### 6.2 机制图示例（Fig.2 结构）

```
controversial_call
  │ writes: perceived_unfairness, match_tension
  │ sets: CONTROVERSIAL_CALL_VISIBLE
  ▼
viral_clip_published
  │ waits: CONTROVERSIAL_CALL_VISIBLE
  │ resources: media_attention_budget
  ▼
media_blame_frame
  ...
```

---

## 7. 可复现性清单

- [ ] `results/reproducibility/manifest.json`：所有 run 的 config hash
- [ ] 固定 `random_seed`（若敏感性分析用随机采样）
- [ ] `requirements.txt` 锁定版本
- [ ] 一键复现脚本：

```bash
bash scripts/reproduce_all.sh
# 预期：实验 1/2/3 + 敏感性 + 图表，耗时 < 30min
```

- [ ] README 含最小复现说明

---

## 8. 论文结构建议

### 8.1 章节映射

| 章节 | 内容来源 |
|------|----------|
| Introduction | [00-完整方案.md](./00-完整方案.md) 定位 + RQ |
| Related Work | 媒体框架、人群风险、因果仿真、可解释 AI |
| Method | Kernel + Mechanism Spec + Evidence 三层 |
| Experiments | 实验 1/2/3 + 敏感性 |
| Case Studies | S1+W1, S3+W0 |
| Discussion | 局限：机制参数、文本抽取误差 |
| Conclusion | trace-first 贡献总结 |

### 8.2 贡献点表述（可直接引用）

1. 提出 trace-first 运行时因果推演框架，将文本证据与因果执行分离
2. 设计可审计的 Mechanism Spec（reads/writes/waits/resources/emits）
3. 实现 Reverse Debugger，支持 why_blocked、diff_trace、cut points
4. 在世界杯情景下验证：比 LLM 直接推演更具可追踪性与干预可比较性

---

## 9. 任务清单总览

### Week 1

- [ ] 消融实验 A1–A6 实现与运行
- [ ] 消融汇总表 + Fig.5
- [ ] 敏感性分析脚本 + 初步图

### Week 2

- [ ] LLM baseline 接口 + 5 次运行
- [ ] 五维评分 + Fig.6
- [ ] 2 个案例研究文档

### Week 3

- [ ] 全部论文图表
- [ ] reproducibility 包
- [ ] experiment-report.md 初稿
- [ ] 全文图表编号核对

---

## 10. 验收标准（Phase 4 Done / 项目 v1.0）

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 实验 1 完整可复现 | `reproduce_all.sh` |
| 2 | 6 组消融全部完成 | ablation_summary.json |
| 3 | LLM 对比 ≥2 场景 × 2 worlds | experiment_3/ 目录 |
| 4 | 五维评分表产出 | explainability_scores.json |
| 5 | 论文 Fig.1–6 + Table.1–4 就绪 | paper/ 目录 |
| 6 | RQ1–RQ4 均有对应结果段落 | experiment-report.md |
| 7 | 证据层 + Kernel 端到端可演示 | 最终 demo 命令通过 |

---

## 11. 最终演示命令

```bash
# 1. 复现全部实验
bash scripts/reproduce_all.sh

# 2. 文本驱动 + 干预 + 解释
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --feed data/atoms/sample_match_feed.jsonl \
  --world W1 --until 120 --explain \
  --output results/final_demo.json

# 3. LLM 对比
python -m worldcup_causal_engine.experiments.llm_baseline \
  --scenario S1 --world W0 --runs 5

# 4. 生成论文图表
python scripts/plot_results.py --all --output paper/figures/
```

---

## 12. 已知局限（论文 Discussion 用）

1. 机制参数来自专家/文献区间，非数据驱动估计
2. 文本 Atom 抽取 v0.1 以规则为主，多语言与讽刺未处理
3. 城市/人群模型简化，未做个体级 ABM
4. LLM baseline 受 prompt 设计影响，已尽量固定 schema
5. 未做真实赛事事后校准（可作为 future work）

---

## 13. Future Work

- [ ] 真实世界杯赛后数据校准机制参数
- [ ] 图神经网络学习机制间触发概率（仍保留 trace）
- [ ] 实时 feed 接入与在线编译
- [ ] 多城市空间显式模型
- [ ] 与决策支持系统（DSS）集成

---

*Phase 4 完成后，项目达到 v1.0，可进入论文撰写与投稿准备。*
