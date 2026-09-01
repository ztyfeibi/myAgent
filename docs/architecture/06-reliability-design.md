# 可靠性与异常处理设计 v1.1

> 上游：`00–05`  
> 目标：保证失败时不伪造 Evidence、不无限循环、不因辅助系统故障拖垮在线回答。

---

## 1. 原则

1. 正确拒答优于无证据回答；
2. 故障局部化；
3. Deadline 自顶向下传播；
4. Retry 只处理瞬时且安全重试的操作；
5. Zero Result 与 Failure 分离；
6. 降级路径必须进入 Trace；
7. 可观测性故障不阻塞主业务；
8. 复用 DeerFlow 运行可靠性，不在 RAG Extension 重建一套。

---

## 2. 故障域

```text
Gateway / Run
Agent Model
RAG Tool
Query Expansion
BM25 Retriever
Vector Retriever
Fusion / FastPass
Reranker
Grader
Evidence Sufficiency
Document Read / Artifact
MediaWiki MCP
RagGuard / Answer
Trace / Eval Export
```

一个故障域失败不应默认取消其他独立结果。

---

## 3. Deadline

每次 AgentRun 有总 Deadline。下游调用使用剩余时间计算自己的 Timeout：

```text
AgentRun Deadline
  ├── Model Call
  ├── Tool Call
  │    ├── Query Expansion
  │    ├── BM25 / Vector
  │    ├── Reranker / Grader
  │    └── MCP / Document Read
  └── Final Guard
```

组件不能通过自身 Retry 超过上游 Deadline。

V1 的具体秒数由配置和压测确定，不在架构中写死。

---

## 4. Retry

可重试：

- 网络瞬断；
- 429 / 明确 Rate Limit；
- Provider 5xx；
- 短暂连接断开；
- 只读、幂等 MCP 查询。

不可重试：

- Schema 错误；
- Prompt/Config 错误；
- 权限或认证失败；
- 永久 Not Found；
- 非幂等写 Tool；
- Grounding 不通过；
- Evidence 本身不足。

Retry 必须有限、带退避并计入预算。

---

## 5. Retrieval 降级矩阵

| 故障 | 降级 | 是否可继续 |
|---|---|---|
| Query Expansion | Original Query only | 是 |
| BM25 | Vector only | 是，标记 degraded |
| Vector | BM25 only | 是，标记 degraded |
| BM25 + Vector | 无内部 Evidence | 否，需其他来源或拒答 |
| FastPass | 执行 Reranker | 是 |
| Reranker | Fusion order | 是 |
| Grader | Reranker order | 是 |
| Evidence Normalize | 丢弃非法 Candidate | 视剩余 Evidence |

降级结果仍需 Sufficiency 判断，不能因为“有结果”就回答。

---

## 6. Model Failure

### Query Expansion

失败后使用 Original Query。

### Grader

失败后保留 Reranker 结果，不伪造 Grading Score。

### Sufficiency

结构化输出解析失败时允许一次同模型修复；仍失败则保守 `abstain`，不猜测 Action。

### Answer

模型失败可以按 DeerFlow Provider Policy 重试或 Failover，但新的模型必须使用同一 Evidence Ledger。

### Judge

离线 Judge 失败只影响评估 Case，不影响在线系统。

---

## 7. Tool Failure

Tool Result 必须区分：

```text
success with evidence
success with zero result
partial/degraded success
retryable failure
permanent failure
```

异常堆栈不进入 LLM Context。Agent 只接收结构化错误和可执行的下一步提示。

---

## 8. Document 与 Artifact

- Document Not Found：标记永久失败，允许 Agent 换文档；
- Version Changed：重新读取并生成新 Evidence；
- Artifact 写入失败：不返回虚假 Ref；
- 片段选择失败：可以重新分段一次，不能把全文作为兜底塞给 LLM；
- 超长文档：分章节读取或 Subagent。

---

## 9. MCP

- V1 MCP 只读且幂等；
- MCP Timeout 不取消已有内部 Evidence；
- Raw Result 未通过 Adapter/Review 时不能作为降级 Evidence；
- 中文无可用候选才回退一次英文；
- MediaWiki 全失败后由 Sufficiency 决定其他搜索或拒答；
- 多 MCP Partial Failure 属于后续能力。

---

## 10. Loop Protection

组合使用 DeerFlow 现有 Loop/Tool Progress 能力和 RAG Evidence No-progress：

- 相同 Tool + 相同参数阻止重复；
- 相似 Query 且 Evidence Hash 无新增视为无进展；
- 每轮记录新增 Evidence 数；
- `max_iterations` 为硬上限；
- Tool、MCP、Token 有独立预算；
- 达到上限后只允许回答已有充分证据或拒答。

---

## 11. RagGuard Failure

RagGuard 属于 Strict Grounding 正确性边界：

- Evidence Schema 非法：拒绝登记；
- Citation 不存在：回答修复一次；
- Evidence 不支持段落：回答修复一次；
- 第二次仍失败：Abstention；
- Guard 本身不可用：`knowledge` 模式 Fail Closed，不输出事实答案；
- `general` 模式不受该规则影响。

---

## 12. Cancellation

取消沿用 DeerFlow Run Cancellation：

- 停止新 Tool/Model 调用；
- 尽力取消在途异步任务；
- 不把取消记录成业务 Abstention；
- 已完成 Artifact 保持一致；
- Trace 标记 cancelled；
- 不自动重放非幂等 Tool。

---

## 13. Streaming 与断线

V1 复用 DeerFlow Gateway、Run Store、Checkpoint 和 Stream Bridge 的现有行为。

RAG Extension 只产生语义事件或 Trace，不建设：

- 第二套 SSE Event Store；
- Route Registry；
- Remote Instance Proxy；
- 自研 Snapshot Recovery。

多实例恢复属于低优先级。只有集成测试证明现有 DeerFlow 无法满足部署目标时再新增设计。

---

## 14. Persistence Failure

- Run/Checkpoint 关键写入失败：Run 失败，不声称完成；
- Evidence Ledger 登记失败：依赖该 Evidence 的回答禁止输出；
- Final Answer 持久化失败：返回可识别临时错误，不能写一半状态；
- Retrieval Trace 写入失败：在线回答可继续，标记 observability degraded；
- Eval Result 写入失败：只失败该 EvalRun。

---

## 15. Backpressure 与并发

需要独立限制：

- 并发 AgentRun；
- 每 Run Retriever 并发；
- Model/Reranker 并发；
- Document Read 大对象并发；
- MCP 并发；
- Eval Runner 并发。

在线流量优先于离线评估。Eval Runner 不能耗尽线上 Provider Budget。

---

## 16. Circuit Breaker

可用于持续失败的外部依赖：

- Knowledge Backend；
- Model Provider；
- Reranker；
- MediaWiki MCP。

Circuit Open 后返回结构化不可用状态，由 Agent 选择其他来源或拒答。V1 可以先用简单失败计数和冷却时间，不要求完整平台。

---

## 17. 错误分类

```text
NO_RESULT
TIMEOUT
RATE_LIMITED
AUTHENTICATION
PERMISSION_DENIED
NOT_FOUND
INVALID_SCHEMA
UPSTREAM_FAILURE
CONFIGURATION
GROUNDING_FAILED
BUDGET_EXHAUSTED
CANCELLED
```

业务无答案使用 Abstention，不伪装成 500；基础设施失败也不能伪装成“知识库没有答案”。

---

## 18. Observability Failure

LangSmith/Langfuse、日志、指标或 Retrieval Trace Export 失败时：

- 记录本地最小错误；
- 不重试到超过 Run Deadline；
- 不阻塞 Answer；
- 在 Run Summary 标记 observability degraded。

Grounding Guard 不属于可忽略的可观测性组件。

---

## 19. 关键指标

- Tool / Retriever Error Rate；
- Degraded Retrieval Rate；
- Empty Result Rate；
- Abstention Rate；
- Grounding Repair / Failure Rate；
- No-progress Stop Rate；
- P95 Agent / Retrieval / Model / MCP Latency；
- Token 和 Tool Call Cost。

阈值在代表性压测后确定。

---

## 20. 验收

1. 单 Retriever 故障可局部降级；
2. 双 Retriever 故障不生成事实答案；
3. Grader/Reranker 失败按固定顺序回退；
4. 全文不会因错误路径进入 Context；
5. MCP 失败不污染 Ledger；
6. 循环能在预算内停止；
7. Guard 失败时 knowledge 模式 Fail Closed；
8. Trace 故障不阻塞业务；
9. 不依赖自研多实例 SSE 设施；
10. 所有降级可追踪。

