# 模块与统一接口规范 v1.1

> 上游：`00–03`  
> 状态：V1 Stable Contract Draft。MCP 私有 Schema 和具体 Provider SDK 不属于稳定接口。

---

## 1. 设计规则

- Domain Model 不依赖数据库、MCP 或模型 SDK；
- Agent 只调用业务 Tool；
- Result 使用结构化 Envelope；
- `zero_result` 与 `failure` 分离；
- 所有可复现运行携带版本；
- 大正文使用 Artifact Reference；
- Score 必须标明语义，不能混用；
- 权限 Contract 延期，不进入 V1 必填字段。

---

## 2. 基础类型

```python
RunId = str
ThreadId = str
ToolCallId = str
RetrievalRunId = str
EvidenceId = str
DocumentId = str
ArtifactId = str
```

所有时间为带时区 ISO-8601 UTC。

---

## 3. Chat Request

```python
class ChatRequest:
    thread_id: str | None
    message: str
    mode: Literal["knowledge", "general"]
    attachments: list[AttachmentRef]
    retrieval_profile: str | None
```

V1 不接受 `mode=auto`。外部 API 不直接暴露 RRF、TopK、FastPass Threshold 等实验参数。

---

## 4. RetrievalRequest

```python
class RetrievalRequest:
    original_query: str
    resolved_query: str
    metadata_filter: dict[str, object] | None
    temporal_constraint: TemporalConstraint | None
    top_k: int
    profile_version: str
    trace_id: str
```

Query Variant 由 RetrievalService 生成，不由 Agent 或 API 调用者传入。

---

## 5. QueryVariant

```python
class QueryVariant:
    variant_id: str
    text: str
    kind: Literal["original", "semantic_variant"]
    weight: float
```

约束：恰好一个 `original`；Semantic Variant 为 1–3 个；降级时可以只有 Original。

---

## 6. RetrieverRequest

```python
class RetrieverRequest:
    retrieval_run_id: str
    query_variant: QueryVariant
    top_k: int
    metadata_filter: dict[str, object] | None
    temporal_constraint: TemporalConstraint | None
```

---

## 7. RetrievalCandidate

```python
class RetrievalCandidate:
    candidate_id: str
    chunk_id: str | None
    document_id: str
    content: str
    title: str | None
    source_uri: str | None
    retriever: Literal["bm25", "vector"]
    query_variant_id: str
    rank: int
    raw_score: float | None
    document_version: str | None
    index_version: str | None
    content_hash: str
    publish_time: datetime | None
    update_time: datetime | None
    metadata: dict[str, object]
```

`raw_score` 只在对应 Retriever 内解释。未来接入 KG 时再扩展 `retriever` 枚举，V1 Contract 不提前声称已有 KG 能力。

---

## 8. FusedCandidate

```python
class CandidateContribution:
    retriever: str
    query_variant_id: str
    rank: int
    query_weight: float
    retriever_weight: float
    rrf_contribution: float

class FusedCandidate:
    candidate_id: str
    content_ref: str
    rrf_score: float
    contributions: list[CandidateContribution]
    matched_queries: list[str]
    matched_retrievers: list[str]
    exact_match_signals: list[str]
```

`rrf_score` 不是 probability/confidence。

---

## 9. Quality Results

```python
class FastPassResult:
    accepted: bool
    accepted_candidate_ids: list[str]
    reason_codes: list[str]

class RerankResult:
    candidate_id: str
    rank: int
    score: float
    model_version: str

class GradingResult:
    candidate_id: str
    accepted: bool
    score: float | None
    reason_code: str
    model_version: str
```

不同阶段 Score 不得互相覆盖。

---

## 10. Evidence

```python
class Evidence:
    evidence_id: str
    content: str
    title: str | None
    source_type: Literal["knowledge", "document", "mcp"]
    source_name: str
    source_uri: str | None
    document_id: str | None
    external_id: str | None
    document_version: str | None
    source_revision: str | None
    index_version: str | None
    content_hash: str
    retrieved_at: datetime
    publish_time: datetime | None
    update_time: datetime | None
    authority: Literal["HIGH", "MEDIUM", "LOW"]
    provenance: dict[str, object]
    artifact_ref: str | None
```

`content` 必须是受控引用片段，不是无界全文。

---

## 11. RetrievalResponse

```python
class RetrievalError:
    component: str
    code: str
    retryable: bool
    message: str

class RetrievalTraceSummary:
    retrieval_run_id: str
    variant_count: int
    candidate_count: int
    evidence_count: int
    fastpass_hit: bool
    degraded: bool
    profile_version: str

class RetrievalResponse:
    evidence: list[Evidence]
    trace: RetrievalTraceSummary
    degraded: bool
    errors: list[RetrievalError]
```

`evidence=[]` 且 `errors=[]` 表示真实零结果；存在 Retriever Failure 时必须出现在 `errors`。

---

## 12. EvidenceSufficiency

```python
class EvidenceSufficiency:
    sufficient: bool
    reason: str
    next_action: Literal[
        "answer",
        "search_again",
        "read_document",
        "abstain",
    ]
```

一致性规则：

- `sufficient=true` 时 `next_action=answer`；
- `sufficient=false` 时不能 `answer`；
- 不存在另一套 Status Enum。

---

## 13. Tool Result Envelope

```python
class ToolError:
    code: str
    message: str
    retryable: bool
    component: str | None

class ToolResult[T]:
    ok: bool
    data: T | None
    error: ToolError | None
    trace_id: str
    tool_call_id: str
    artifact_refs: list[str]
```

`ok=false` 时不得同时返回看似有效的 Evidence。

---

## 14. Tool Contracts

### `knowledge_search`

```python
knowledge_search(query, metadata_filter=None, temporal_constraint=None)
    -> ToolResult[RetrievalResponse]
```

### `document_read`

```python
document_read(document_id, focus)
    -> ToolResult[DocumentReadResult]

class DocumentReadResult:
    document_id: str
    selected_evidence: list[Evidence]
    artifact_ref: str
    document_version: str
    content_hash: str
```

### Wikipedia

```text
wikipedia_search
wikipedia_read
```

最终参数和 MediaWiki 页面标识在 Adapter 开发时根据实际 MCP Schema 确定；稳定输出仍为 Candidate/Evidence/Artifact Contract。

---

## 15. Document Contract

```python
class DocumentDescriptor:
    document_id: str
    title: str | None
    document_version: str
    content_hash: str
    source_uri: str | None
    publish_time: datetime | None
    update_time: datetime | None
    metadata: dict[str, object]

class RawDocument:
    descriptor: DocumentDescriptor
    content: str
    content_type: str
```

`RawDocument.content` 只在代码/Artifact 路径流转，不作为默认 ToolMessage 字段。

---

## 16. Ledger Entry

```python
class EvidenceLedgerEntry:
    evidence: Evidence
    run_id: str
    tool_call_id: str
    retrieval_run_id: str | None
    validation_status: Literal["valid", "rejected"]
    registered_at: datetime
```

Ledger 为 Run-scoped，不是知识库主数据。

---

## 17. Citation 与回答

```python
class Citation:
    evidence_id: str
    source_name: str
    title: str | None
    source_uri: str | None
    source_revision: str | None

class AnswerParagraph:
    text: str
    evidence_ids: list[str]

class FinalAnswer:
    paragraphs: list[AnswerParagraph]
    citations: list[Citation]
    abstained: bool
    abstention_reason: str | None
```

V1 使用段落级引用，不建立 Claim Entity。

---

## 18. Artifact

```python
class ArtifactRef:
    artifact_id: str
    media_type: str
    content_hash: str
    size_bytes: int
    created_at: datetime
```

完整文档和 MCP 长正文通过 Artifact 返回，前端可以直接展示或下载，不要求再次经过 LLM。

---

## 19. Trace Correlation

以下 ID 必须可关联：

```text
trace_id
thread_id
run_id
tool_call_id
retrieval_run_id
evidence_id
artifact_id
profile_version
```

---

## 20. Provider Protocol

```python
class Retriever(Protocol):
    async def search(self, request: RetrieverRequest) -> list[RetrievalCandidate]: ...

class RetrievalService(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse: ...

class KnowledgeRepository(Protocol):
    async def bm25_search(...): ...
    async def vector_search(...): ...
    async def read_document(...): ...

class EvidenceReviewer(Protocol):
    async def review(...): ...
```

V1 In-process 实现和 Future Remote 实现遵循相同 Contract。

---

## 21. Config Contract

每次 Run 必须绑定：

```text
profile_id
profile_version
config_hash
prompt_versions
model_versions
index_version
```

Config 文件可编辑，但历史版本语义不可覆盖。

---

## 22. Schema Evolution

- 新字段默认 Optional；
- 删除或改义需要新 Contract Version；
- `metadata` 不得承载已有明确字段；
- Enum 新值需要消费者兼容策略；
- MCP 私有字段只能留在 Adapter/Raw Metadata；
- API 不返回 Secrets、Prompt 全文、内部堆栈和全量 Candidate。

---

## 23. Contract Test

至少覆盖：

- Retriever Candidate 字段完整；
- RRF Contribution 可追溯；
- Retrieval Zero Result 与 Failure；
- Evidence 版本字段；
- Tool Envelope 一致性；
- Artifact 不进入 ToolMessage；
- EvidenceSufficiency 逻辑约束；
- Citation 只能引用 Ledger；
- Profile Version 贯穿。
