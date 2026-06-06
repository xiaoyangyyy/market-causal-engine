# 案例研究：S3 + W0 高温拥挤与沟通资源枯竭

## 场景设定

S3 叠加三重压力：高温（`heat_stress=0.85`）、赛前争议判罚（t=55）、赛后散场（`match_end` t=90），且 `official_comm_channel=0`（官方沟通资源枯竭）。

## Kernel 主导路径

完整系统跑出两条压力耦合链：

**舆论链（早段）**：`controversial_call` → 媒体/谣言机制（幅度受参数约束）

**散场恐慌链（末段）**：
```
match_end → fans_gather → transit_delay → crowd_density_spike
→ queue_overflow → crowd_push → panic_signal
```

最终恐慌风险显著高于 S1（`panic` 可达 0.5+），验证 RQ1 中「比赛事件 → 线下风险」的多路径并发。

## 资源瓶颈

W1 干预（官方澄清）在 S3 下必然失败：`resource_bottlenecks` 记录 `official_comm_channel` 多次失败。这与场景设计意图一致——沟通资源枯竭时，澄清干预不可执行。

Reverse `why_blocked` 可直接引用 trace，无需事后猜测。

## 与 LLM 对比

LLM baseline 常将「高温」「拥挤」「交通」并列叙述，但容易：

- 跳过 `transit_delay → crowd_density_spike` 中间机制
- 声称澄清「可能有效」，忽略 channel=0 的硬约束

Kernel 的 mechanism spec 强制澄清机制调用 `acquire(official_comm_channel)`，使失败可验证。

## 结论（RQ2 / RQ4）

S3 证明：**运行时条件（flags + resources）** 而非单一情绪分数决定路径是否可走通。消融 A2（without_resources）可进一步展示：移除资源层后澄清「虚假成功」，风险被低估——支撑 trace-first 引擎的必要性。
