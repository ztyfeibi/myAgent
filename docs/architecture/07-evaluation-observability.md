# 测试、评估与可观测性设计 v1.1

> 上游：`00–06`  
> 目标：用少量核心指标证明 Retrieval、Agent 和最终回答有效，并能通过 Trace 定位问题。

---

## 1. 分层评估

```text
Retriever
→ Retrieval Quality Pipeline
→ Agent Search Policy
→ Final Answer / Grounding / Abstention
→ Cost / Latency / Reliability
```

不能只看最终回答，也不能用回答分数替代 Retrieval Recall。

---

## 2. V1 核心指标

### Retrieval

- `Evidence Recall@10 / Hit@10`；
- `Gold Evidence Retention Rate`。

### Agent

- `Search Recovery Rate`。

### Answer

- `Answer Accuracy`；
- `Groundedness`；
- `Abstention F1`。

### Engineering

- `P95 Latency`；
- `Token Cost`。

这 8 项进入 V1 核心报告，避免看板过载。

---

## 3. 诊断指标

按问题需要开启，不作为所有发布的硬门槛：

- NDCG@10 或 MRR；
- Precision@K；
- Reranker/Grader 前后 Recall 与 Precision；
- Evidence Sufficiency Accuracy；
- Premature Stop Rate；
- 平均 Search Round；
- 平均 Tool Calls；
- Query Expansion 增益；
- FastPass Hit / False-positive Rate；
- Degraded Run Rate。

NDCG 和 MRR 通常选择一个主排序诊断指标，不要求同时成为核心指标。

---

## 4. Future KG 指标

只有实现 KG 后启用：

- KG Incremental Evidence Recall Gain；
- Multi-hop Evidence Recall；
- Multi-hop Answer Accuracy。

KG 指标不得出现在 V1 无 KG 的验收结论中。

---

## 5. 数据集组合

### MIRACL-zh

用于中文检索、BM25/Vector/RRF 与 Query Expansion 消融。必须导入其 Corpus 并保留 Qrels。

### HotpotQA

用于多文档、补搜、Evidence Sufficiency 和 Answer Accuracy。

### RAGBench

用于 Groundedness、Context Relevance 和 Answer 支持性。它不单独证明真实检索效果。

### SQuAD 2.0

可选拒答集，用于有答案/无答案判断；它偏给定 Context，不单独证明 Retrieval。

### 项目领域小集

后期约 30 题，采用半自动生成：

```text
抽取真实文档
→ LLM 生成问题、参考答案、Gold 文档/Chunk
→ 人工只做通过/驳回/少量修正
→ 增加少量无答案与版本问题
```

公开集证明通用能力，小领域集证明实际 Adapter、切分、索引和 Citation 有效。

---

## 6. 数据接入原则

公开数据集必须走真实链路：

```text
Dataset Corpus
→ External Knowledge Base Ingestion
→ BM25 / Vector Index
→ knowledge API
→ Agent / Retrieval / Answer
```

不能在端到端评估中直接把 Gold Context 塞给 LLM；只有专门的 Answer-only 子评估可以这样做。

---

## 7. Dataset Contract

```json
{
  "case_id": "...",
  "question": "...",
  "mode": "knowledge",
  "gold_answer": "...",
  "gold_evidence": ["doc_or_chunk_id"],
  "answerable": true,
  "tags": ["multi_hop", "temporal"],
  "dataset_version": "..."
}
```

允许不同数据集缺少部分字段，但缺少 Gold Evidence 的 Case 不能计算 Retrieval Recall。

---

## 8. Retrieval Ground Truth

Gold Evidence 可以是：

- Chunk ID；
- Document ID；
- Supporting Fact / Section；
- 经过映射的 Corpus Passage ID。

报告必须注明评估粒度，不能把 Document Hit 和 Chunk Hit 混成同一 Recall。

---

## 9. Gold Evidence Retention

用于防止质量阶段“更干净但删掉正确证据”：

```text
进入阶段前存在 Gold Evidence 的 Case 中，
阶段后仍保留 Gold Evidence 的比例
```

分别统计 Fusion、Reranker、Grader 和 FastPass。

---

## 10. Search Recovery Rate

用于证明 Agent 补搜有效：

```text
首轮证据不足且后续新增 Gold Evidence 的 Case
------------------------------------------------
首轮证据不足且存在可恢复路径的 Case
```

同时报告 Premature Stop 和平均 Search Round，避免通过无边界搜索刷高 Recovery。

---

## 11. Abstention

推荐 `Abstention F1`，区分：

- 应回答且回答；
- 应回答但拒答；
- 应拒答且拒答；
- 应拒答却回答。

无答案样本必须覆盖：

- Corpus 中确实不存在；
- Gold 文档被移除；
- Evidence 冲突无法解决；
- 来源失败且没有安全替代；
- 问题超出知识范围。

---

## 12. LLM Judge

用于 Answer Accuracy、Groundedness、Sufficiency 等语义指标。

要求：

- Judge Model 固定版本；
- Prompt 固定版本；
- Temperature 和结构化输出固定；
- Judge 只读取评估所需问题、Gold、实际 Evidence 和 Answer；
- Judge 不参与被测 Agent；
- 保存 Score、Reason 和原始结构化结果；
- Judge 失败只失败该 Case。

开发阶段不强制人工复核；最终验收抽查低分、临界分和争议样本。

---

## 13. Eval Runner

Eval Runner 是独立离线模块，不进入 Agent Graph。

职责：

1. 加载 Dataset Version；
2. 指定 RetrievalProfile；
3. 通过真实 `knowledge` 接口执行；
4. 根据 `trace_id` 读取 Retrieval Trace；
5. 计算确定性指标；
6. 调用 Judge；
7. 聚合指标和分组结果；
8. 输出 JSON/CSV/Markdown 报告。

Eval Runner 不写生产 Conversation 和 Long-term Memory。

---

## 14. Ablation

至少支持：

```text
BM25 only
Vector only
BM25 + Vector + Weighted RRF
+ Query Expansion
+ Reranker
+ Grading
+ FastPass
Agent single-shot vs multi-round
Internal only vs Internal + MediaWiki
```

每次对比只改变目标变量，并固定 Dataset、Index、Model、Prompt 和其他 Profile。

---

## 15. 结果版本

每个 EvalRun 记录：

```text
dataset_version
profile_version / config_hash
index_version
code build
agent assembly fingerprint
prompt versions
model/reranker versions
judge version
started_at / completed_at
```

缺少关键版本时报告必须标记不可严格复现。

---

## 16. 可观测性架构

复用 DeerFlow：

- Request Trace ID；
- Run/Thread Metadata；
- LangSmith / Langfuse Callback；
- Token/Cost/Run 统计。

RAG Extension 增加嵌套 Span：

```text
rag.run
├── query_expansion
├── retrieval.bm25
├── retrieval.vector
├── fusion
├── fastpass
├── reranker
├── grading
├── evidence_registration
├── evidence_sufficiency
├── document_read
├── mcp_external_evidence
└── grounding_guard
```

V1 不另建 OpenTelemetry 平台。

---

## 17. Span 与结构化 Trace 分工

Span 保存：

- 时间；
- 数量；
- 状态；
- 版本；
- 是否降级；
- Reason Code。

结构化 Retrieval Trace 保存：

- Query Variant；
- Candidate；
- RRF Contribution；
- Stage Decision；
- Evidence；
- 错误详情。

完整文档、Secrets、Raw Prompt 和大正文不进入 Span。

---

## 18. Trace Sampling

- Eval Run：100% 详细 Trace；
- 开发环境：默认详细；
- 生产成功请求：可采样；
- Error、Abstention、Grounding Failure、Degraded Run：提高保留率；
- 内容字段遵守数据最小化。

具体比例由部署环境决定。

---

## 19. 报告结构

```text
1. Run Identity and Versions
2. Core Metrics
3. Dataset/Tag Breakdown
4. Ablation Comparison
5. Error Taxonomy
6. Latency and Cost
7. Representative Failure Cases
8. Limitations
```

不以单个总分掩盖 Retrieval、Agent 与 Answer 的差异。

---

## 20. V1 验收

1. 三个主公开集可通过 Adapter 加载；
2. Corpus 经过真实知识库索引；
3. 8 个核心指标可计算；
4. Retrieval 与 Answer 可分层；
5. Agent 补搜有 Recovery 指标；
6. Abstention 使用正反样本；
7. Judge 可复现且不参与被测系统；
8. Eval Runner 调用真实接口；
9. Trace 可以还原关键 Pipeline；
10. 报告同时给出效果、延迟和成本。

