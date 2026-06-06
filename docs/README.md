# 世界杯因果推演引擎 — 文档索引

## 文档列表

| 文档 | 说明 |
|------|------|
| [00-完整方案.md](./00-完整方案.md) | 全局方案：定位、架构、数据、机制、实验、输出格式 |
| [phase-01-核心引擎与主链路.md](./phase-01-核心引擎与主链路.md) | Phase 1：Kernel + 主链路 A + S1 W0/W1 |
| [phase-02-逆向调试与干预实验.md](./phase-02-逆向调试与干预实验.md) | Phase 2：Reverse Debugger + S1–S3 × W0–W5 |
| [phase-03-文本证据层.md](./phase-03-文本证据层.md) | Phase 3：Atom → Cluster → Compiled Event |
| [phase-04-完整实验与论文输出.md](./phase-04-完整实验与论文输出.md) | Phase 4：消融、LLM 对比、论文图表 |

## 推荐阅读顺序

1. 先读 **00-完整方案.md** 把握全局
2. 按阶段实施：**phase-01 → phase-02 → phase-03 → phase-04**
3. 每阶段以文档末尾 **验收标准** 作为完成判定

## 实施路线

```
Phase 1 (1–2周)   Kernel + 链路A + S1
    ↓
Phase 2 (1–2周)   Reverse + 链路B/C + 实验1
    ↓
Phase 3 (1–2周)   文本证据层
    ↓
Phase 4 (2–3周)   消融 + LLM对比 + 论文
```
