# 复合检索 Agent 开发实施指南 v1.1

> 文档编号：08  
> 上游文档：`00-architecture-baseline.md` 至 `07-evaluation-observability.md`  
> 技术基座：现有 DeerFlow 代码库 + RAG Extension  
> 本文只规定开发顺序、阶段产物和验收边界，不展开具体业务代码。

---

## 1. 实施原则

1. **扩展 DeerFlow，不复制其核心代码。** Gateway、会话、Checkpoint、SSE、MCP、Skill、Sandbox、Memory、Subagent 均优先复用。
2. **先打通最小纵向闭环，再提高检索质量。** 每个阶段都应独立可测试、可回退。
3. **契约先于实现。** `Evidence`、`RetrievalTrace`、`EvidenceSufficiency`、`RetrievalProfile` 等模型先稳定，再接具体引擎。
4. **严格区分事实与流程。** Tool、Skill、Agent 推理均不是证据；只有通过证据化流程并登记到 Ledger 的内容才能支撑 `knowledge` 模式事实回答。
5. **配置与版本可复现。** 一次运行所使用的 Profile、模型、Prompt、索引和数据集版本均可追踪。
6. **不在 V1 提前实现预留项。** 权限体系、自研多实例 SSE 恢复、KG、图片向量检索、自动模式选择和统一跨源打分均不进入当前开发范围。

---

## 2. 推荐模块边界

RAG 能力以 DeerFlow Extension 形式接入，建议保持以下逻辑边界；实际目录可根据仓库现状微调。

```text
rag_extension/
├── extension.py              # DeerFlow 扩展入口与组件注册
├── modes/                    # knowledge / general 显式模式配置
├── contracts/                # Evidence、Trace、Profile、Sufficiency
├── retrieval/                # 扩展、召回、融合、精排、审查、去重
├── tools/                    # knowledge_search、document_read、外部证据包装工具
├── guard/                    # Evidence Ledger 与 RagGuardMiddleware
├── artifacts/                # 长文原文与非上下文返回物
├── mcp_evidence/             # MCP 结果证据化；不重建 MCP 协议栈
└── evaluation/               # 离线 Runner、指标、Judge、报告
```

依赖方向固定为：

```text
DeerFlow Runtime
      ↓ extension hooks
RAG Tools / RagGuard
      ↓
RetrievalService contracts
      ↓
Retrieval pipeline + External KB adapter
```

`RetrievalService` 不反向依赖 DeerFlow Agent 状态，便于单测和未来远程化。

---

## 3. 分阶段实施与验收

阶段编号表示依赖顺序，不表示工期。

### 阶段 0：基线核验

工作内容：

- 固定所基于的 DeerFlow 版本或提交；
- 跑通原生对话、Tool、MCP、Skill、Sandbox、Checkpoint 与 SSE；
- 记录扩展注册点、中间件顺序和现有观测入口。

验收：未加载 RAG Extension 时，DeerFlow 原有行为不变；形成可重复的基线检查清单。

### 阶段 1：扩展骨架与显式模式

工作内容：

- 注册 RAG Extension、Tools、Middleware 和 Service；
- 提供显式 `general`、`knowledge` 模式；
- `general` 保持原生行为，`knowledge` 启用严格证据约束。

验收：两种模式可由同一会话入口明确选择；不存在 V1 自动模式判断。

### 阶段 2：核心契约与运行版本

工作内容：

- 定义 `Evidence`、`EvidenceSource`、`EvidenceSufficiency`、`RetrievalTrace`；
- 定义不可变 `RetrievalProfile` 及其版本或哈希；
- 贯通 `run_id`、`trace_id`、`conversation_id` 和证据来源版本。

验收：契约可序列化并进行 Schema 校验；同一 Profile 可重放；Evidence 必须保留来源、定位和版本信息。

### 阶段 3：外部知识库适配与双路原始召回

工作内容：

- 实现 `RetrievalService` 及外部知识库 Adapter；
- 接通 BM25、Vector 原始召回与文档读取；
- 保留每路原始排名、来源定位和索引版本。

验收：两路可独立调用；任一路失败时另一路仍可返回；Adapter 不包含 Agent 决策。

### 阶段 4：查询扩展与融合

工作内容：

- 每次内部搜索生成“原问题 + 1–3 个语义变体”；
- 保留实体、日期、数字和标识符，不引入新事实；
- 原问题权重高于变体；使用 Weighted RRF 融合并去重。

验收：扩展失败自动回退原问题；Trace 可解释每个候选来自哪个查询和检索器；不直接比较 BM25 与 Vector 原始分数。

### 阶段 5：检索质量流水线

工作内容：

- 实现 FastPass、Reranker、LLM Grading；
- FastPass 使用多路一致性、精确匹配和元数据约束，不使用固定原始分数阈值；
- Reranker 与 Grader 均围绕原始问题判断。

验收：每阶段输入、输出、去留原因和耗时可追踪；Reranker 失败回退 Fusion，Grader 失败回退 Reranker；两者都不可用时不得生成无证据事实回答。

### 阶段 6：Evidence Ledger 与 RagGuard

工作内容：

- `knowledge_search` 只登记通过证据化流程的 Evidence；
- `RagGuardMiddleware` 统一完成 Tool 结果校验、Ledger 登记、最终 grounding 与引用校验；
- 不合格答案最多修复一次，仍失败则拒答。

验收：事实性结论可回溯到 Ledger；伪造引用、越界引用和无证据结论被阻断；Skill 指令不会被当成证据。

### 阶段 7：确定性文档读取与 Artifact

工作内容：

- `document_read` 通过代码读取完整正文；
- 只把与当前查询相关的段落送入模型；
- 完整正文作为 Artifact 返回，不自动进入 LLM Context。

验收：用户能获得完整原文；上下文预算不会随整篇文档线性膨胀；引用仍指向稳定文档位置。

### 阶段 8：Agent 搜索闭环

工作内容：

- Evidence Sufficiency 只输出 `sufficient`、`reason`、`next_action`；
- 支持 `answer | search_again | read_document | abstain`；
- 加入最大轮数、重复查询/证据检测和 no-progress 终止。

验收：证据不足时能补搜或读文档；重复无进展会提前停止；达到预算后明确拒答而非猜测。

### 阶段 9：MediaWiki MCP 外部证据

工作内容：

- 复用 DeerFlow MCP 连接、发现与执行能力；
- 暴露面向 Agent 的 `wikipedia_search`、`wikipedia_read` 证据工具；
- 对外部结果执行硬校验、语义 Review、Evidence 转换和 Ledger 登记；
- 中文 Wikipedia 无可用结果时只允许一次英文回退。

验收：MCP 不参与内部统一 Rerank；外部原文长内容以 Artifact 返回；失败不拖垮内部检索；精确工具参数和返回 Schema 在开发该阶段时再定。

### 阶段 10：离线评测与观测闭环

工作内容：

- 通过真实知识 API 运行 MIRACL-zh、HotpotQA、RAGBench，SQuAD2 作为可选拒答补充；
- 计算已确认的 8 个核心指标；
- 接入 DeerFlow Trace 与现有 LangSmith/Langfuse 能力，增加 RAG 结构化 Trace；
- LLM Judge 固定模型、Prompt 和输出理由，与生产回答模型解耦。

验收：一次运行能产出可复现报告，关联 Profile、模型、Prompt、索引和数据集版本；公开数据实际进入本系统知识库，不绕过检索链路。

### 阶段 11：后续工作流增强

在核心闭环稳定后，可新增 `knowledge-research` Skill，编排搜索、读文档、外部补充和冲突整理。Skill 只描述工作流，不扩大 Evidence 边界。其具体提示词和目录结构在实现阶段确定。

---

## 4. 测试层次

| 层次 | 重点 |
|---|---|
| Contract Test | Schema、枚举、版本字段、序列化兼容性 |
| Unit Test | 查询扩展约束、Weighted RRF、去重、FastPass、预算与回退 |
| Adapter Test | 外部 KB/MCP 异构结果归一化、超时、空结果与错误映射 |
| Integration Test | DeerFlow → Tool → RetrievalService → Ledger → Answer 全链路 |
| Grounding Test | 无证据、错误引用、冲突证据、修复失败与拒答 |
| Evaluation Regression | 8 个核心指标、延迟和成本相对基线的变化 |

V1 至少保留以下故障用例：单检索器失败、Reranker 失败、Grader 失败、MCP 超时、外部内容提示注入、重复搜索、长文超预算和索引版本变化。

---

## 5. 配置与环境

配置分三类管理：

- **DeerFlow 原生配置**：模型、MCP、Sandbox、Checkpoint、SSE 等；
- **RetrievalProfile**：扩展策略、召回数量、融合、FastPass、Reranker、Grader、预算；
- **运行绑定版本**：Prompt、模型、索引、数据集和外部来源版本。

敏感凭据仅通过 DeerFlow 既有凭据或部署机制注入，不写入 Profile、Trace、评测报告或文档示例。

配置变更必须有版本标识。用于对比评测的 Profile 在单次运行期间不可变。

---

## 6. 联调顺序

建议按最短故障定位路径联调：

```text
外部 KB 原始召回
→ RetrievalService 单次检索
→ knowledge_search Tool
→ Evidence Ledger
→ 单轮 knowledge 回答
→ 多轮补搜 / document_read
→ MediaWiki MCP 补充
→ 离线评测
```

不要在底层召回尚不可解释时直接调 Agent Prompt，也不要用手工拼接的“看似正确答案”替代真实知识 API 联调。

---

## 7. 每阶段完成定义

一个阶段只有同时满足以下条件才算完成：

1. 契约与实际行为一致；
2. 主路径和已定义回退路径均有自动化测试；
3. Trace 能解释关键决策；
4. 未破坏 `general` 模式及 DeerFlow 原生能力；
5. 文档已更新，不依赖口头约定；
6. 可以回退到上一阶段的稳定状态。

---

## 8. V1 明确不做

- 不提取或复制 DeerFlow 核心代码另起 Runtime；
- 不自研 MCP Client、通用 Router 或并行 Executor；
- 不实现自动 `knowledge/general` 模式选择；
- 不实现权限模型；
- 不实现自研多实例 SSE 恢复系统；
- 不实现 KG 主链路和 KG 专项指标；
- 不实现图片向量索引；
- 不把全部文档正文塞进模型；
- 不把不同来源的未校准分数合成统一可信度；
- 不在当前阶段确定 MediaWiki MCP 的全部字段和精确调用签名。

这些边界变化必须先更新 `00-architecture-baseline.md`，再进入实现。
