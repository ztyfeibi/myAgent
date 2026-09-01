# 数据与存储设计 v1.1

> 上游：`00–04`  
> 原则：数据只保留一个权威来源；RAG Extension 不复制知识库主数据，也不重建 DeerFlow Run Persistence。

---

## 1. 数据归属

| 数据 | 权威存储 | 说明 |
|---|---|---|
| Thread / Message / Run | DeerFlow Persistence | 复用现有能力 |
| LangGraph Checkpoint | DeerFlow Checkpointer | Agent 恢复状态 |
| Document / Chunk / Metadata | External Knowledge Base | RAG 不复制主数据 |
| BM25 / Vector Index | External Knowledge Base | 可重建索引 |
| Evidence Ledger | Run State / Checkpoint | Run-scoped |
| 完整文档 / MCP 长正文 | Artifact Store | 通过引用进入状态 |
| Retrieval Trace | Structured Trace Store / Artifact | 评估和诊断 |
| RetrievalProfile | Versioned Config | 不可变语义 |
| Eval Dataset / Results | Offline Eval Storage | 不污染在线会话 |
| Long-term Preference | DeerFlow Memory | 非严格证据 |

---

## 2. 不重复持久化原则

RAG Extension 不建立自己的：

- Document 主表；
- Chunk 主表；
- Vector Index；
- Thread / Message 主表；
- MCP Server 配置主表；
- Trace Platform。

必要时只保存外部对象 ID、版本、哈希和 Artifact 引用。

---

## 3. Run State

Checkpoint 中只保存可恢复的小状态：

```text
mode
original_query / resolved_query
iteration
search_history
document_read_history
mcp_call_history
evidence_ledger references
last_evidence_evaluation
profile_version
trace_id
```

禁止写入：

- 完整文档正文；
- MCP 完整页面；
- 全量 Raw Candidate；
- 大模型完整 Trace；
- 二进制附件。

---

## 4. Evidence Ledger 存储

Ledger Entry 至少保存：

```text
evidence_id
run_id
tool_call_id
retrieval_run_id
source identity
bounded excerpt
document/source revision
index version
content hash
retrieved_at
authority
artifact_ref
validation status
```

Ledger 生命周期默认与 Run/Thread 一致。跨会话不直接复用 Ledger。

---

## 5. Evidence 去重与历史复用

同一 Run 内优先使用：

```text
source identity + version + content_hash
```

同一会话历史 Evidence 只有在以下条件均满足时复用：

- 同一用户和知识范围；
- Document/Source Version 未变化；
- Content Hash 一致；
- 来源仍可访问；
- 不是历史 Assistant Answer。

---

## 6. Artifact

Artifact 用于：

- 完整文档；
- MediaWiki 完整页面或大结果；
- Retrieval Trace 详情；
- Eval 报告；
- 用户可直接查看的生成文件。

Artifact Metadata：

```text
artifact_id
owner run/thread
media_type
content_hash
size_bytes
source identity
source revision
created_at
retention policy
```

写入应原子完成；状态中只保存 `artifact_id`。

---

## 7. Retrieval Trace

Retrieval Trace 与 DeerFlow Trace 通过 `trace_id` 关联，但不把所有细节塞入通用 Span。

建议结构：

```text
RetrievalRun
├── request and profile versions
├── query variants
├── retriever attempts
├── candidates and contributions
├── quality stage decisions
├── evidence output
└── errors / degradation / latency
```

在线会话只保存 Trace Summary；完整结构进入专用 JSON/对象存储或可查询表。

---

## 8. RetrievalProfile

Profile 文件计算 `config_hash`，运行记录：

```text
profile_id
profile_version
config_hash
created_at
model/prompt versions
```

修改配置产生新版本，不能覆盖历史版本含义。V1 不建设数据库配置中心。

---

## 9. Evaluation Storage

离线评估数据与在线数据分离：

```text
Dataset
DatasetVersion
EvalRun
EvalCaseResult
MetricResult
JudgeResult
Artifact
```

每个 EvalRun 绑定：

- Dataset Version；
- RetrievalProfile Version；
- Agent / Prompt / Model Version；
- Index Version；
- Code Build；
- Judge Version。

Eval Runner 可以引用在线 Trace Schema，但不写入生产 Thread/Memory。

---

## 10. Document Version

每个内部 Evidence 至少携带：

```text
document_version
index_version
content_hash
retrieved_at
```

MCP Evidence 使用：

```text
source_revision
content_hash
retrieved_at
```

版本缺失时必须明确标记，不得伪造稳定版本。

---

## 11. Conversation 与 Memory

Conversation 存储用户和 Assistant 可见消息；隐藏的 Raw Candidate、Judge Prompt、完整 Evidence 不应作为聊天消息持久化。

Long-term Memory 仅保存偏好和稳定上下文。V1 禁止自动把知识回答写成长期事实记忆。

---

## 12. Retention

建议按类别配置：

- Thread/Run：沿用 DeerFlow 策略；
- Evidence Ledger：随 Run 或审计策略；
- 完整 Artifact：按大小和用途设置 TTL；
- Retrieval Trace：开发/评估长留，生产可采样；
- Eval Dataset/Result：版本化长期保留；
- Secrets：不进入上述存储。

V1 不写死具体保留天数。

---

## 13. 缓存

允许缓存：

- Query Expansion；
- Retriever Result；
- Reranker/Grader Result；
- Document Artifact；
- MediaWiki Read Result。

Cache Key 必须包含与结果语义有关的版本：

```text
query / focus
profile version
model version
index/source revision
content hash
```

缓存命中不能绕过 Evidence Version 和 RagGuard 校验。

---

## 14. 权限延期边界

V1 不实现复杂权限模型。存储 Contract 不将 `PermissionContext` 设为必填。

未来加入权限时，必须在 Knowledge Adapter 查询前过滤，并把授权范围纳入 Cache Key 和 Evidence Reuse 条件；该能力不影响当前 V1 数据模型主干。

---

## 15. 多实例与 SSE

优先使用 DeerFlow 已有 Run、Checkpoint 和 Stream 能力。RAG Extension 不持久化第二套 SSE Event Log、Route Registry 或 Snapshot Recovery 状态。

只有实际部署证明 DeerFlow 现有能力不足时，才单独设计增强方案；当前属于低优先级。

---

## 16. 一致性与失败

- Evidence 写入 Ledger 失败时不得生成依赖该 Evidence 的最终回答；
- Artifact 写入失败时不返回失效 Artifact Ref；
- Trace 写入失败可以降级，不阻塞回答；
- Eval 写入失败不影响在线 Run；
- Profile 找不到历史版本时标记运行不可复现；
- External KB 仍是文档事实源，RAG 缓存不能反向覆盖它。

---

## 17. 验收

1. 文档和 Chunk 没有第二份主数据；
2. Run State 不包含无界正文；
3. Ledger 可关联 Tool/Run/Version；
4. Artifact 可校验 Hash；
5. Retrieval Trace 与通用 Trace 可关联；
6. Eval 与生产会话隔离；
7. 历史配置可复现；
8. 权限和多实例延期能力不是 V1 数据依赖。

