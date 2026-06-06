# Phase 5–6：Proposal–Verification 运行时 + 可分叉因果账本

## 架构原则

**Atom ≠ Event**；**Proposal ≠ Execution**。未经验证机制契约（Contract）的提案不得进入 Kernel 执行队列。

```
Proposer (LLM / 规则 / 场景)
        │
        ▼
    Proposal ──► MechanismVerifier ──► accepted? ──► emit + run
                        │                    │
                        ▼                    ▼
                  trace: verification    trace: blocked
                        │
                        ▼
                 CausalLedger (snapshot per executed event)
                        │
                        ▼
                 fork_at(kind) + interventions → counterfactual branch
```

## Phase 5 — 契约与验证

| 模块 | 路径 | 职责 |
|------|------|------|
| Contract IR | `worldcup_causal_engine/ir/contract.py` | `StateConstraint`、`Contract`、`data/contracts/v0.1.json` |
| Proposal IR | `worldcup_causal_engine/ir/proposal.py` | 不可信提案 + `VerificationResult` |
| Verifier VM | `worldcup_causal_engine/vm/verifier.py` | `unknown_kind` / `missing_flags` / `pre_condition` / `resource_shortage` |
| LLM Proposer | `worldcup_causal_engine/proposers/llm.py` | 仅 `kernel.propose()`，不直接 `commit` |
| Kernel | `kernel.propose()` + `run()` 内 `use_contracts` | trace 记录 `proposal` / `verification` / `blocked` |

### KernelConfig 新增开关

- `use_contracts: bool = True` — `run()` 前契约校验
- `use_causal_ledger: bool = True` — 每次 `executed` 写入快照

### 演示：S3 + LLM 提案

`official_comm_channel=0` 时，LLM 提案 `official_clarification` 在验证阶段被拒绝，`reason_code=resource_shortage`，完整记录在 trace。

```bash
python -m worldcup_causal_engine.main --scenario data/scenarios/S3_heat_crowd_comm_delay.json --propose-demo
```

## Phase 6 — 可分叉因果账本

| 模块 | 路径 | 职责 |
|------|------|------|
| Snapshot | `ledger/snapshot.py` | 状态 / 标志 / 资源 / 待执行队列 |
| Log | `ledger/log.py` | 追加式账本，内容寻址 `entry_id` |
| Fork | `ledger/fork.py` | `fork_at`、`replay_fork`、`diff_branches` |

### 分叉语义

1. 基线运行（如 S1 W0）产生 `causal_ledger` 与每步快照（含 `pending_events`）。
2. `fork_at(ledger, "rumor_amplified")` 取该事件**之前**最后一步快照。
3. 恢复快照 + 待执行队列，注入干预（如 W1 `official_clarification` t=87），`run(until)` 继续。
4. **等价性**：S1 在 `rumor_amplified` 前分叉 + W1 ≈ 完整 `run_scenario(S1, W1)`（路径与 `final_risk` 一致）。

```python
from worldcup_causal_engine.ledger.fork import replay_fork_from_scenario

_, fork, full = replay_fork_from_scenario(
    "data/scenarios/S1_controversial_call_high_density.json",
    baseline_world="W0",
    fork_before_kind="rumor_amplified",
    intervention_world="W1",
)
assert fork.dominant_path == full["dominant_path"]
```

## Trace 扩展字段

- `proposal_id` / `proposer` / `verification` — Phase 5 审计
- `ledger_entry_id` — Phase 6 账本交叉引用

## 与 Architecture 2.0 的关系

Phase 5–6 为 **Proposal–Verification Split** 与 **Forkable Causal Ledger** 的落地实现；Phase 7–8（证据类型系统、MDG、约束校准）在此基础上扩展，不重复实现机制层。
