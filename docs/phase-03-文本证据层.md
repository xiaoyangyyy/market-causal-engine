# Phase 3：文本证据层

**阶段目标**：实现 Atom → Claim Cluster → Compiled Event 管道，使系统能从新闻/社媒文本驱动因果 Kernel，贯彻 “Observe many, compile once” 原则。  
**预计工期**：1–2 周  
**前置依赖**：[Phase 2：逆向调试与干预实验](./phase-02-逆向调试与干预实验.md)  
**后续阶段**：[Phase 4：完整实验与论文输出](./phase-04-完整实验与论文输出.md)

---

## 1. 阶段交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 证据层 | `worldcup_causal_engine/evidence.py` | Atom 录入、Cluster 聚合、证据账本 |
| 编译器 | `worldcup_causal_engine/compiler.py` | Cluster → Compiled Event |
| 编译规则 | `data/compiler_rules/` | claim_type → event kind 映射与阈值 |
| 样例数据 | `data/atoms/sample_match_feed.jsonl` | 模拟帖文流 |
| 集成入口 | `main.py --feed` | 文本流驱动模式 |
| 测试 | `tests/test_evidence.py`, `tests/test_compiler.py` | |

---

## 2. 设计原则（本阶段必须遵守）

1. **Atom 不能直接 emit event，不能改 state**
2. **同一 claim 多次出现只更新 Cluster 统计量，不重复编译**
3. **只有达到编译阈值的 Cluster 才产出一条 Compiled Event**
4. **Compiled Event 的 `cause` 必须指向 `claim_cluster:{id}`**
5. **证据账本与因果 trace 分离存储，可交叉引用**

---

## 3. 任务清单

### 3.1 Atom 模型 (`evidence.py`)

```python
@dataclass
class Atom:
    atom_id: str
    source_id: str
    time: int              # 比赛分钟
    claim_type: str
    target: str
    actor_group: str
    emotion: str
    confidence: float
    raw_text: str
```

- [ ] Atom 数据类与 JSON 序列化
- [ ] `EvidenceLedger.ingest(atom)` 录入单条 atom
- [ ] 自动生成 atom_id（若缺失）
- [ ] 时间窗口规范化（match minute 整数）

### 3.2 Claim Cluster 聚合

#### 3.2.1 Cluster Key 规则

```
{claim_type}|{actor_group}|{target}|{match_id}|{time_bucket}
```

- `time_bucket`：每 10 分钟一桶，如 `t20_30` 表示 20–30 分钟
- 相同 key 的 atom 并入同一 cluster

#### 3.2.2 Cluster 统计量更新

| 字段 | 更新规则 |
|------|----------|
| `support_count` | +1 每条 atom |
| `unique_sources` | source_id 去重计数 |
| `velocity` | 滑动窗口内 support_count / window_size |
| `emotion_intensity` | atom emotion 映射为数值后 EMA |
| `confidence` | 加权平均（按 atom confidence） |
| `contestation` | 存在反向 claim_type 时升高 |

- [ ] `ClaimCluster` 数据类
- [ ] `cluster_key(atom, match_id)` 函数
- [ ] `update_cluster(cluster, atom)` 增量更新
- [ ] `EvidenceLedger.clusters` 索引

### 3.3 去重与噪声过滤

- [ ] 同 source_id + 同 claim_type + 同 time_bucket 的重复 atom 只计一次
- [ ] confidence < 0.3 的 atom 进入 ledger 但不更新 cluster（可配置）
- [ ] 可选：simhash / 文本相似度去重（v0.1 可用 raw_text 精确去重）

### 3.4 证据账本

```python
class EvidenceLedger:
    atoms: list[Atom]
    clusters: dict[str, ClaimCluster]
    compiled_cluster_ids: set[str]   # 已编译，防重复

    def ingest(self, atom: Atom) -> str | None: ...  # 返回 touched cluster_id
    def get_cluster(self, cluster_id: str) -> ClaimCluster: ...
    def to_dict(self) -> dict: ...
```

- [ ] 账本持久化 `save(path)` / `load(path)`
- [ ] 与 kernel trace 独立，但 Compiled Event 的 cause 可链接 cluster_id

### 3.5 Compiler (`compiler.py`)

#### 3.5.1 编译规则配置

`data/compiler_rules/v0.1.json`：

```json
{
  "blame_referee": {
    "emit_kind": "media_blame_frame",
    "thresholds": {
      "support_count": 50,
      "unique_sources": 20,
      "velocity": 0.4,
      "confidence": 0.6
    },
    "payload_mapping": {
      "target": "referee",
      "intensity": "velocity",
      "confidence": "confidence",
      "dominant_claim": "blame_referee"
    },
    "priority": 2
  },
  "rumor_clip_shared": {
    "emit_kind": "viral_clip_published",
    "thresholds": {
      "support_count": 30,
      "velocity": 0.5
    },
    "priority": 2
  },
  "fan_conflict_report": {
    "emit_kind": "opposing_fans_contact",
    "thresholds": {
      "support_count": 10,
      "emotion_intensity": 0.7
    },
    "priority": 1
  }
}
```

- [ ] `CompilerRules` 加载与查询
- [ ] `should_compile(cluster, rule)` 阈值检查
- [ ] `compile(cluster, rule) -> CompiledEvent` 产出 typed event
- [ ] 已编译 cluster 标记，不再二次编译（除非 `recompile_policy=velocity_increase_50%` 可选）

#### 3.5.2 Compiled Event 结构

```python
@dataclass
class CompiledEvent:
    kind: str
    time: int
    priority: int
    payload: dict
    cause: list[str]   # ["claim_cluster:C22"]
```

- [ ] `Compiler.try_compile(ledger) -> list[CompiledEvent]` 扫描所有未编译达标 cluster
- [ ] 编译结果通过 `kernel.emit()` 注入，**不直接 commit state**

### 3.6 文本流驱动模式

#### 3.6.1 Feed 处理流程

```
JSONL feed → ingest atoms → update clusters
    → try_compile → emit compiled events into kernel queue
    → kernel.run(until=next_feed_time or end)
```

- [ ] `FeedRunner`：按 atom.time 顺序处理
- [ ] 与场景触发器共存：scenario trigger 先注入，feed 持续驱动 media/social 类事件
- [ ] CLI：`--feed data/atoms/sample_match_feed.jsonl`

#### 3.6.2 样例 Feed

创建 `data/atoms/sample_match_feed.jsonl`（争议判罚后 20–40 分钟帖文）：

- 200+ 条 `blame_referee` atoms（多 source）
- 50+ 条 `rumor_clip_shared`
- 少量反向 `defend_referee`（测 contestation）
- 若干 `fan_conflict_report`

### 3.7 Claim Type 词表（v0.1）

| claim_type | 说明 | 编译为 |
|------------|------|--------|
| `blame_referee` | 指责裁判 | media_blame_frame |
| `blame_player` | 指责球员 | media_blame_frame |
| `rumor_clip_shared` | 传播争议剪辑 | viral_clip_published |
| `official_statement` | 官方声明提及 | 不直接编译，降低阈值权重 |
| `fan_conflict_report` | 线下冲突目击 | opposing_fans_contact |
| `transit_complaint` | 交通抱怨 | transit_delay（可选） |
| `defend_referee` | 为裁判辩护 | 升 contestation，阻断编译 |

- [ ] claim_type 枚举文档
- [ ] emotion → intensity 映射表（anger=0.9, joy=0.2, …）

### 3.8 与 LLM 抽取的接口（可选扩展）

若使用 LLM 从 raw text 抽 atom：

```python
def extract_atoms(raw_text: str, metadata: dict) -> list[Atom]: ...
```

- [ ] 定义稳定 JSON schema 供 LLM 输出
- [ ] v0.1 可用手工标注 feed，不强制接 LLM
- [ ] 记录 `extractor_version` 在 atom metadata

---

## 4. 测试用例

### 4.1 Evidence 单测

- [ ] 100 条同 key atom → 1 cluster，support_count=100
- [ ] 不同 source 正确计入 unique_sources
- [ ] 重复帖文（同 source+text）不计入
- [ ] contestation：defend_referee 升高 contestation

### 4.2 Compiler 单测

- [ ] 未达阈值不编译
- [ ] 达标产出正确 kind 和 payload
- [ ] 同一 cluster 只编译一次
- [ ] cause 含 `claim_cluster:{id}`

### 4.3 端到端

- [ ] S1 场景 + sample feed → kernel 跑通链路 A
- [ ] 无 feed 时仅 scenario trigger 仍可运行（回归 Phase 1/2）
- [ ] trace 中 media_blame_frame 的 cause 指向 cluster
- [ ] reverse.trace_path 可回溯到 cluster_id

---

## 5. 验收标准（Phase 3 Done）

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | Atom 不直接改 state | 代码审查 + 单测 |
| 2 | 200 条相似 atom 只编译 1 次 event | support_count 测试 |
| 3 | Feed 模式跑通 S1 完整链路 | 端到端测试 |
| 4 | trace cause 可链接 evidence ledger | reverse 回溯测试 |
| 5 | 证据账本可独立 save/load | 持久化测试 |

---

## 6. 输出示例

编译产出：

```json
{
  "kind": "media_blame_frame",
  "time": 32,
  "priority": 2,
  "payload": {
    "target": "referee",
    "intensity": 0.72,
    "confidence": 0.78,
    "dominant_claim": "blame_referee"
  },
  "cause": ["claim_cluster:C22"]
}
```

证据账本摘要：

```json
{
  "ledger_id": "match_M12_feed",
  "total_atoms": 483,
  "total_clusters": 12,
  "compiled_clusters": 3,
  "top_clusters": [
    {
      "cluster_id": "C22",
      "claim_type": "blame_referee",
      "support_count": 483,
      "velocity": 0.72,
      "compiled_to": "media_blame_frame"
    }
  ]
}
```

---

## 7. 本阶段不做

- 实时 Twitter/API 抓取（用手工 JSONL 代替）
- 复杂 NLP 聚类（v0.1 用规则 key）
- 多语言支持（先英文 feed）
- 消融实验（Phase 4）

---

## 8. 建议实施日程

| 天 | 任务 |
|----|------|
| D1 | Atom + EvidenceLedger 基础 |
| D2 | Cluster 聚合 + 去重 |
| D3 | Compiler 规则 + try_compile |
| D4 | FeedRunner + main.py 集成 |
| D5 | 样例 feed 制作 + 端到端联调 |
| D6–D7 | 测试、trace 交叉引用、文档 |

---

## 9. CLI 示例

```bash
# 文本流驱动
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --feed data/atoms/sample_match_feed.jsonl \
  --world W0 \
  --until 120 \
  --output results/S1_feed_W0.json \
  --ledger-output results/S1_feed_W0_ledger.json
```

---

*完成 Phase 3 后进入 [Phase 4](./phase-04-完整实验与论文输出.md)。*
