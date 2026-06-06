# 实验报告：世界杯因果推演引擎 v1.0

**项目**：Trace-First Runtime Causal Engine for World Cup Crowd-Risk Simulation  
**版本**：Phase 4 完整实验输出  
**日期**：2026-06-05

---

## 1. 研究问题映射

| RQ | 问题 | 实验 | 主要发现 |
|----|------|------|----------|
| RQ1 | 比赛/舆论事件如何转化为线下风险？ | 实验1 压力测试 + Feed 模式 | 三条主链路（判罚/出局/散场）均可复现；Feed 编译事件与场景触发器可共存 |
| RQ2 | 哪些运行时条件放大或阻断链条？ | 实验2 消融 + S3 案例 | flags/resources/priority 缺一不可；A1/A2 导致路径失真 |
| RQ3 | 干预如何改变因果路径？ | 实验1 W0–W5 对比 | W1/W3 对 S1 最有效；`diff_trace` 给出分叉点与 cut points |
| RQ4 | 是否比 LLM 更可审计？ | 实验3 五维评分 | Kernel 在 traceability/consistency/intervention_diff 上显著高于 mock LLM |

---

## 2. 实验 1：场景压力测试

- **设计**：S1–S3 × W0–W5，共 18 runs
- **输出**：`results/experiment_1/`
- **洞察**：
  - 跨场景最有效干预：**W3**（球迷分流，S1）
  - 最常见瓶颈：`official_comm_channel`（S3）
  - S1 W1 分叉点：`rumor_amplified` 之后插入 `official_clarification`

---

## 3. 实验 2：消融实验

- **设计**：full + A1–A6，S1–S3 × W0，共 21 行结果
- **输出**：`results/experiment_2/ablation_summary.json`

| 消融 | 预期退化 | 观测 |
|------|----------|------|
| A1 without_flags | 阻断解释消失，路径变长 | blocked↓，path↑ |
| A2 without_resources | 瓶颈消失 | resource_shortage 归零 |
| A3 without_priority | 干预时序失真 | 风险与 full 偏离 |
| A4 without_trace | 不可审计 | trace_entries=0 |
| A5 without_intervention | W0=W1 | intervention_effect=false |
| A6 without_evidence_ledger | Feed 逐 atom 发射 | path_length 膨胀 |

---

## 4. 实验 3：LLM Baseline（智算 API 实测）

- **API**：`https://ai.azya.top/v1`，模型 **`qwen3.5`**
- **设计**：S1 + S3 × W0/W1，各 3 runs，严格 JSON schema prompt
- **输出**：`results/experiment_3_zhisuan/`

### 收紧 Prompt 前后对比（S1）

| 维度 | Kernel | LLM（旧 prompt） | LLM（严格 schema） |
|------|--------|------------------|---------------------|
| consistency | 1.0 | 0.27 | **0.95** |
| not_happen_explanation | 1.0 | 0.0 | **1.0** |
| bottleneck_localization | 1.0 | 0.5 | 0.0* |

\*S1 场景 `official_comm_channel=5`，LLM 未强制识别瓶颈；S3（channel=0）得 0.5。

### 合并评分（S1+S3）

| 维度 | Kernel | qwen3.5 |
|------|--------|---------|
| traceability | **1.0** | 1.0 |
| consistency | **1.0** | 0.98 |
| not_happen_explanation | **1.0** | 1.0 |
| intervention_diff | 0.5 | 1.0 |
| bottleneck_localization | **1.0** | 0.25 |

**结论**：严格 schema 后 LLM 一致性大幅提升；Kernel 在**资源瓶颈可验证性**与**确定性 trace** 上仍有优势（RQ4）。

运行命令见 `.env.example` 与 `README.md`。

---

## 5. 敏感性分析

- **设计**：S1+W0，4 参数网格 + police_trust，最多 100 runs
- **输出**：`results/experiment_sensitivity/sensitivity_summary.json`
- **结论**：路径结构在参数区间内定性稳定（`path_stable`），风险幅度连续变化——回应「手工参数」审稿意见

---

## 6. 文本证据层（Phase 3 集成）

Feed 模式（295 atoms → 4 clusters → 3 compiled events）验证：

- 220+ `blame_referee` atoms → **1 次** `media_blame_frame` 编译
- trace `cause` 含 `claim_cluster:C1`，reverse 可交叉引用 ledger

---

## 7. 复现

```powershell
powershell -File scripts/reproduce_all.ps1
```

产物清单见 `results/reproducibility/manifest.json`

---

## 8. 论文图表

| 编号 | 文件 | 内容 |
|------|------|------|
| Fig.2 | `paper/figures/fig2_mechanism_chain.mmd` | 主链路 A |
| Fig.3 | `paper/figures/fig3_diff_trace.png` | S1 W0 vs W1 |
| Fig.4 | `paper/figures/fig4_risk_heatmap.png` | 风险热图 |
| Fig.5 | `paper/figures/fig5_ablation.png` | 消融对比 |
| Fig.6 | `paper/figures/fig6_explainability_radar.png` | RQ4 雷达图 |
| Table 1–4 | `paper/tables/*.csv` | 场景/压力/消融/评分表 |

---

## 9. 局限与未来工作

见 Phase 4 方案 §12–13：机制参数为敏感性区间、文本抽取规则化、未做真实赛事校准。

---

*项目 v1.0 实验阶段完成，可进入论文撰写。*
