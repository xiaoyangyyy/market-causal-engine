# 案例研究：S1 + W1 官方澄清与资源瓶颈

## 场景设定

S1（`S1_controversial_call_high_density`）在 t=70 触发争议判罚，主办城市 fan zone 人群密度高（0.75），警方信任偏低（0.45）。基线世界 W0 不施加干预；W1 在 t=87 注入 `official_clarification`，消耗 `official_comm_channel: 1`。

## Kernel 观测结果

W0 主导风险路径为：

```
controversial_call → viral_clip_published → media_blame_frame → rumor_amplified
→ offline_mood_shift → opposing_fans_contact → verbal_conflict
```

最终 `verbal_conflict = 0.52`，`scuffle = 0.12`。

W1 在 `rumor_amplified` 之后执行官方澄清，清除 `RUMOR_SPIKE`，阻断 `offline_mood_shift`（blocked: `missing_flags:RUMOR_SPIKE`）。最终口头冲突风险降至 0。

`diff_trace` 分叉点为 `rumor_amplified`：W1 独有路径含 `official_clarification`，W0 独有路径含线下升级链。

## 资源瓶颈实验

将 `official_comm_channel` 设为 0（S3 配置同类）时，W1 的 `official_clarification` 被 trace 记录为 `resource_shortage:official_comm_channel`，澄清不生效，风险与 W0 接近。Reverse Debugger 可精确回答「为何澄清失败」。

## LLM Baseline 对比

Mock LLM 能给出合理的路径叙述，但：

- 无法产出与 trace 一一对应的 `event_id` 因果链
- 对资源瓶颈的识别依赖 prompt 推断，不能证明 `acquire` 失败
- 5 次运行路径 Jaccard 一致性低于 Kernel 的确定性输出

## 结论（RQ3 / RQ4）

官方澄清在「谣言峰值后、情绪传导前」是最有效切断点之一。Kernel 通过 trace 证明该窗口有效性及资源约束失败模式；这是纯 LLM 推演难以审计的优势。
