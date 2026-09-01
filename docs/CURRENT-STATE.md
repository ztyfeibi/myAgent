# 当前实现清单（CURRENT-STATE）

本文只回答一个问题：**代码现在真实具备什么**。

- 不写未来架构、不写"计划支持"、不写"设计上应该"。
- 每一条"已实现"都必须能落到代码行、测试文件、测试结果或配置文件上。
- 与 `docs/task/TASK-001-rag-extension-foundation.md` 的分工：TASK-001 是**任务记录**（做过什么、验收结论），本文是**现状快照**（现在有什么、缺口在哪）。

核对时间：2026-08-30 起，2026-08-31 定稿
核对基线：deer-flow `a0eead4e` / rag-extension `d034a3a`，两工作区均 clean
核对方式：逐文件 Read + 全仓 grep + 三份代码副本逐字节比对

---

## 本文结构

| 部分 | 章节 | 内容 |
|---|---|---|
| **第一部分：能力清单** | §0 – §12 + 附录 | 逐项陈述"有什么 / 没什么"，每条绑定证据 |
| **第二部分：As-Is 架构** | §13 – §23 | 组件关系、三种模式时序、数据流、所有权与安装链路；只画已落地结构 |

两部分的口径定义（§0 的 7 种状态）完全共用。第二部分所有图中的元素都必须是 §10 边界表里"已实现"或"保留原生"的组件。

---

# 第一部分：能力清单

---

## 0. 状态口径定义

本文所有结论只能使用以下 7 种口径之一。禁止使用"支持""完成""已具备"等无界定词。

| # | 口径 | 含义 | 判定标准 |
|---|---|---|---|
| 1 | **已实现并验证** | 代码存在 + 有自动化测试覆盖 + 测试当前通过 | 可指出实现文件 **且** 测试文件 **且** 测试结果 |
| 2 | **已实现但仅单元测试** | 代码存在 + 有测试，但只测到单元边界，未走真实链路 | 测试用桩件替代了链路上的真实部件 |
| 3 | **已接线但未运行验证** | 配置/代码已就位，但从未在真实运行中观察过 | 只有配置文件或代码阅读作为依据 |
| 4 | **保留 DeerFlow 原生能力** | 本次工作未触碰，沿用上游既有实现 | 可指出"未被修改"的证据（如提交 diff 不含该文件） |
| 5 | **Stub / 临时实现** | 结构正确但内容为固定值，不可用于真实业务 | 代码内有 `_STUB_` 常量或等价标记 |
| 6 | **未实现** | 代码中不存在 | 全仓 grep 零命中 |
| 7 | **不在当前范围** | 明确延期到后续任务 | TASK-001 §3 已列明 |

---

## 1. 代码存在的位置与提交基线

### 1.1 三份副本及其关系

| 副本 | 路径 | 来源 | 是否入库 |
|---|---|:--:|---|
| 开发源 | `rag-extension/` | 手写 | 是（独立仓库，HEAD `d034a3a`） |
| 安装快照 | `deer-flow/backend/extensions/sources/rag-extension/` | `make extension-install` 复制而来 | **否**，被 `.gitignore` 第 75–77 行排除 |
| 已安装副本 | `deer-flow/backend/.venv/Lib/site-packages/rag_extension/` | 非 editable 安装 | 否 |

**实测结论（口径 1）**：三份副本的 8 个模块 `__init__/modes/middleware/tools/retrieval/contracts/ledger/lifecycle` 逐字节相同（`diff -q` 全部 SAME）。

**这个事实的实际含义**：测试导入的是 `.venv` 里的已安装副本，不是 `rag-extension/` 源码。改动源码后必须重新 `make extension-install` 才会被测试看到。

### 1.2 TASK-001 在 deer-flow 仓库的入库改动

只改了 **3 个生产文件**，再无其他：

| 文件 | 改动 | 提交 |
|---|---|---|
| `.gitignore` | +4 行（排除 `backend/extensions/`） | `a0eead4e` |
| `backend/pyproject.toml` | +5 / -1 行（声明 rag-extension 依赖） | `a0eead4e` |
| `backend/uv.lock` | +25 / -1 行 | `a0eead4e` |

另有一批**仅测试文件**的提交：`602ecb82`（gateway，408 行 / 8 例）、`848e1157`（trace + contracts + integration + middleware，40 例）、`fdadff7b`（modes，14 例，重建）。

**提交范围偏差（已知，用户已决定"保持现状，仅作记录"）**：`602ecb82` 在恢复 gateway 测试的同时，误带入了 `.gitignore` 的 2 行无关改动（新增 `.codegraph`），与本次任务无关。

**这是第 9 步"原生能力保留"最硬的证据**：除 `.gitignore` / `backend/pyproject.toml` / `backend/uv.lock` 三个文件外，deer-flow 的生产代码（含 MCP、skills、sandbox、memory、gateway 全部实现）零改动。

### 1.3 一个必须知道的事实：运行时接线不入库

| 事实 | 证据 |
|---|---|
| `config.yaml` 被 git 忽略 | `.gitignore:33` → `git check-ignore -v config.yaml` 命中；`git ls-files` 不认识该文件 |
| RAG 运行时接线写在 `config.yaml` | 第 1574–1593 行 |
| `config.example.yaml` **没有** RAG 接线 | grep `rag_extension` 零命中（只有上游的 `my_company.deerflow_middlewares` 示例） |

**结论**：克隆仓库的人装完 extension 后，RAG 不会自动启用，必须手工往自己的 `config.yaml` 加那一段。这属于口径 3 的风险区——接线只在本机存在，无版本控制、无同步机制。

### 1.4 环境残留物（已于 2026-08-31 清理）

| 残留项 | 清理前状态 | 处理 |
|---|---|---|
| `backend/extensions/sources/.rag-extension.remove-3ubzl2z9/` | `extension-remove` 中断留下的完整 `source/` 快照 | **已删除**。删除前逐字节比对确认是**旧版本**（`contracts.py` 231 行 vs 权威 291 行，缺 2.8 阶段加的冻结语义），非唯一副本 |
| `backend/.pytest_cache`、`backend/.ruff_cache` | 工具缓存，导致 `git status` 常显脏 | **已删除**（可再生） |
| `rag-extension/.pytest_cache`、`.ruff_cache` | 同上 | **已删除** |
| 7 处 `__pycache__/` | 编译产物 | **已删除**（`.venv` 内的未动） |
| `.tmp-uv-resync.log` / `.tmp-uv-resync2.log` | 根目录临时日志 | **已删除** |
| `.stabilize/uv-cache/` | 缓存子目录 | **已删除** |

**保留项（不视为垃圾）**：

| 保留项 | 理由 |
|---|---|
| `.stabilize/2026-08-30-2119/`（381KB） | 事故现场快照。已验证其中 `recovered/test_rag_extension_gateway.py` 与入库版逐字节相同、`rag-extension/` 源码副本仅 `.pyc` 有差异，技术上冗余；但含 `git-diff-deerflow.patch` 与 `MANIFEST.md`，是事故恢复过程的**唯一现场证据**，建议长期保留 |
| `.tmp-uv-tool/` | 钉版 uv 0.11.1 所在位置，DeerFlow 相关工作的必需工具（本机默认 uv 为 0.11.11，不可用于本仓库） |

清理后复跑验证：六个 RAG 测试 **62 passed**、rag-extension 包内 **7 passed**，`deer-flow` 与 `rag-extension` 两工作区 `git status` 均干净。

---

## 2. RAG Extension 包结构（8 个模块）

| 模块 | 行数 | 当前职责 | 是否生产实现 | 测试证据 |
|---|---:|---|---|---|
| `__init__.py` | 29 | `@extension(api="0.2.0", name="rag-extension")` 装饰 `install()`；`enabled=False` 时直接 return；**只**注册 `RagTaskLifecycle` | 生产实现 | `tests/test_plugin.py::test_install_registers_task_lifecycle`、`test_disabled_extension_registers_nothing`；`tests/test_entry_point.py`（entry point 可被 `importlib.metadata` 发现） |
| `modes.py` | 54 | 模式常量与解析：`RAG_MODE_CONTEXT_KEY="rag_mode"`、`RAG_MODES=("general","knowledge")`；`normalize_rag_mode()` / `resolve_rag_mode()`；非法值抛 `RagModeError`（`code="invalid_rag_mode"`） | 生产实现 | `backend/tests/test_rag_extension_modes.py`（14 例，含 fail-closed、大小写敏感、空白不宽容、非字符串拒绝、不修改入参 context） |
| `middleware.py` | 145 | `KnowledgeModeMiddleware`：knowledge 模式注入 policy SystemMessage；general 模式从绑定里摘掉 `knowledge_search` schema 并拦截走私调用；构造时校验插件已加载，否则抛 `ExtensionNotWiredError` | 生产实现 | `backend/tests/test_rag_extension_middleware.py`（13 例）+ `test_rag_extension_gateway.py`（8 场景）+ `test_rag_extension_integration.py`（4 例） |
| `tools.py` | 111 | `knowledge_search` 工具：模式校验 → 构造 `RetrievalRequest` → 调 `StubRetrievalService` → 打 run/thread 溯源 → 入账 ledger → 返回 `ToolResult` JSON 信封 | 生产外壳 + **Stub 内核** | `test_rag_extension_integration.py::test_tool_defends_against_non_knowledge_mode_without_middleware`、`test_06_stub_tool_executes_and_produces_a_tool_message` |
| `retrieval.py` | 105 | `StubRetrievalService.retrieve()`：返回 3 条硬编码文档（`E1/E2/E3`），SHA-256 content_hash，`uuid4()` 生成 retrieval_run_id | **Stub 实现**（口径 5） | `test_rag_extension_contracts.py::test_stub_is_deterministic_except_retrieval_timestamps` |
| `contracts.py` | 291 | 8 类冻结数据契约（详见 §6） | 生产实现 | `test_rag_extension_contracts.py`（18 例） |
| `ledger.py` | 94 | `RagTaskLedger`（run 作用域证据账本，带 `Lock`）+ `RagExtensionStats`（app 作用域累计） | 生产实现 | `test_plugin.py::test_lifecycle_allocates_ledger_and_absorbs_stats`、`test_ledger_snapshot_keeps_run_and_tool_call_linkage` |
| `lifecycle.py` | 34 | `RagTaskLifecycle`：`on_task_start` 分配 ledger，`on_task_stop` 回收并 absorb 到 app 层统计 | 生产实现 | `test_plugin.py::test_lifecycle_allocates_ledger_and_absorbs_stats`（断言 `searches==1`、`evidence_registered==3`、`tasks=={"completed":1}`） |

**口径总结**：8 个模块中 7 个是生产实现，1 个（`retrieval.py`）是 Stub。Stub 是**有意设计**（TASK-001 目标是验证契约闭环，不是接真实知识库），不是半成品。

---

## 3. 扩展加载方式

| 环节 | 现状 | 口径 |
|---|---|---|
| Entry point 声明 | `rag-extension/pyproject.toml`：`[project.entry-points."deerflow.extensions"] rag-extension = "rag_extension:install"` | 已实现并验证 |
| 安装命令 | `make extension-install SOURCE=../rag-extension` → 复制到 `backend/extensions/sources/` → 非 editable 安装进 `.venv` | 已实现并验证（三副本逐字节相同） |
| 依赖声明 | `backend/pyproject.toml:114`：`rag-extension = { path = "extensions/sources/rag-extension" }`（第 58 行亦列入 source 组） | 已接线 |
| 锁文件 | `backend/uv.lock:4091-4093`：`source = { directory = "extensions/sources/rag-extension" }`；第 914 行 `[package.metadata] extensions = [...]` | 已接线 |
| 插件注册 | `config.yaml:1586-1592` 的 `plugins:` 块 → `use: rag_extension:install`，`enabled: true`、`required: true` | **已接线但未入库**（见 §1.3） |
| 中间件注册 | `config.yaml:1582-1584` 的 `extensions.middlewares:` → `rag_extension.middleware:KnowledgeModeMiddleware` | **已接线但未入库**（见 §1.3） |
| 加载自检 | `KnowledgeModeMiddleware.__init__` 调 `_extension_plugin_loaded()`，插件未加载则抛 `ExtensionNotWiredError`（错误信息明确要求"两者是一个开关"） | 已实现并验证（`test_middleware_fails_closed_when_plugin_not_loaded`） |

### 3.1 为什么中间件不走插件贡献

`middleware.py` 文件头注释与 `README.md` §"Why the middleware is not plugin-contributed" 说明：插件贡献的中间件被包进 `IsolatedMiddleware`，其 wrap 钩子**只能观察、不能替换请求**。而 general 模式要从模型绑定里摘掉 `knowledge_search` schema，必须 `request.override(tools=...)`，因此必须走 operator-trusted 的 `extensions.middlewares` 配置（与上游 `DeferredToolFilterMiddleware` 同一模式）。

这一条是**架构约束**，不是实现选择。已由 `test_01` / `test_05` / `test_08` 验证：只有走 `extensions.middlewares` 时 schema 才会被摘掉。

### 3.2 干净环境重建路径（未实测，口径 3）

`pyproject.toml` 与 `uv.lock` 都指向 `extensions/sources/rag-extension`，而该目录被 gitignore。因此**干净 clone 后不能直接 `uv sync --locked`**——本地路径依赖不存在，会失败。

推断的正确顺序是：`make extension-install SOURCE=<rag-extension 路径>` → `uv sync`。**这条路径本次未实际执行验证**（只在既有环境上跑过 `uv lock --check` 通过）。

---

## 4. 请求与模式链路

### 4.1 事实表

| 问题 | 答案 | 证据 |
|---|---|---|
| 模式从哪传入 | `config["context"]["rag_mode"]`，由 worker 从 `body.config.context` **原样拷贝**进 `runtime.context` | `test_rag_extension_gateway.py:209-211` 注释 + `test_05` 断言 `context["rag_mode"]` |
| 合法值 | 仅 `"general"` / `"knowledge"`（`RAG_MODES` 元组） | `modes.py` |
| 缺省值 | `general`。缺失 / 空 context / 无 `rag_mode` 键 / 值为 `None` 四种情况都解析为 general | `test_rag_extension_modes.py` 前 4 例 + `test_05` 断言 `"rag_mode" not in default.contexts[0]["context"]` |
| 非法值怎么处理 | 抛 `RagModeError`（继承 `ValueError`，`code="invalid_rag_mode"`，携带 `value` 与 `expected`） | `test_unknown_mode_fails_closed`、`test_empty_string_mode_fails_closed`、`test_non_string_modes_fail_closed`、`test_error_carries_value_code_and_expected_modes` |
| 是否有 auto 模式 | **没有**。代码里不存在任何自动判定逻辑 | `RAG_MODES` 只有两值；失败用例专门用 `"auto"` 做反例 |
| 谁读取 rag_mode | **仅 3 处**：`middleware._prepare_model_request`、`middleware._blocked_tool_message`、`tools.knowledge_search` | 见下方 §4.2 |
| 是否改了 Gateway 专属结构 | **没有** | 见 §4.2 |

### 4.2 关键事实：Gateway 完全不认识 `rag_mode`

全仓 grep 结果：

```
backend/app/          → rag_mode 零命中
backend/packages/     → rag_mode 零命中
backend/tests/        → 仅在 6 个 RAG 测试文件中出现
```

**含义**：

1. Gateway / HTTP 层**不做** `rag_mode` 校验。模式校验发生在中间件内部，即**运行期**，不是请求入口。
2. 非法模式的失败形态是 **run 失败**（`RunStatus.error`，`record.error` 含 `"invalid rag_mode"`），**不是 HTTP 422**。已由 `test_03_invalid_mode_is_rejected` 和 trace 的 `test_invalid_mode_is_recorded_as_run_error_in_run_events` 验证。
3. 失败是 **fail-closed 且在模型调用之前**：`test_03` 断言 `result.bound == []`、`result.messages == []`。

### 4.3 文档与实现不一致（必须记录）

`rag-extension/README.md:56` 写着：

> Invalid values are rejected with HTTP 422 at the run boundary.

**这句话与当前代码不符。** 代码里没有任何 422 逻辑，也没有 run-boundary 校验。失败发生在运行期中间件，客户端看到的是 run error。

这是一条**文档错误**，不是代码 bug（fail-closed 的行为本身是对的）。建议修正 README 措辞，但本次不动（本次只写清单，不改代码/文档）。

---

## 5. general 模式：三层严格区分

用户要求这一步不能把"代码没改"写成"全部实测通过"。这里分三层陈述。

### 5.1 层一：架构上没有改动 —— 成立

- 除 `.gitignore` / `pyproject.toml` / `uv.lock` 三个文件外，deer-flow 生产代码零改动（§1.2 提交 diff 证据）。
- general 模式的实现方式是"**新增一个中间件**"，不是"修改原生链路"。中间件只在 knowledge 分支注入消息，general 分支的唯一动作是从绑定列表里**删掉自己加的那个工具**。
- `test_01` 实证：general 模式下 `bound[0] == ["native_tool"]`，即模型可见工具集**只剩原生工具**。
- `test_08` 实证：扩展完全禁用时（无插件、无中间件），即使请求带 `rag_mode="knowledge"`，行为仍是 `bound[0] == ["native_tool"]`，退化为纯原生。

### 5.2 层二：有自动化回归测试 —— 成立，但测试用的是桩件

覆盖 general 模式的用例：

| 文件 | 用例 | 断言要点 |
|---|---|---|
| `test_rag_extension_gateway.py` | `test_01`、`test_05`（default 分支）、`test_08` | 绑定只剩原生工具、无 policy 消息、无 knowledge_search 出现在发布载荷、ledger 为 None |
| `test_rag_extension_integration.py` | `test_general_mode_hides_schema_and_blocks_smuggled_call`、`test_absent_mode_defaults_to_native_toolset`、`test_tool_defends_against_non_knowledge_mode_without_middleware` | schema 被摘、走私调用被拦（`status="error"`）、无中间件时工具自己也会拒绝 |
| `test_rag_extension_middleware.py` | `test_general_mode_filters_knowledge_search_schema_only`、`test_absent_mode_defaults_to_native_toolset`、`test_general_mode_with_only_knowledge_tool_filters_to_empty`、`test_wrap_tool_call_blocks_*`、`test_awrap_tool_call_blocks_*`、`test_wrap_tool_call_leaves_native_tools_untouched_in_general_mode` | 只摘 knowledge_search、其他工具不动、同步/异步两条路径都拦 |
| `test_rag_extension_trace.py` | `test_general_mode_leaves_no_knowledge_evidence_in_run_events`、`test_extension_disabled_leaves_no_knowledge_evidence_in_run_events` | 事件流中无 `llm.tool.result`、无 `E1` |

**但所有这些用例的"原生工具"是同一个 1 行桩件**：

```python
@as_tool
def native_tool(x: str) -> str:
    "A native DeerFlow tool."
    return x
```

### 5.3 层三：真实 MCP / Skill 运行验证 —— **未做**

| 验证维度 | 状态 |
|---|---|
| 真实 MCP server 接入后 general 模式工具集是否保持不变 | **未验证** |
| 真实 Skill 加载后是否与中间件冲突 | **未验证** |
| 真实 Sandbox 执行路径下 general 模式是否正常 | **未验证** |
| HTTP / SSE 端到端（真实请求打进 Gateway） | **明确不在范围**（TASK-001 §7.2；测试只覆盖到 run 级载荷，注释写明 "HTTP/SSE over HTTP is still out of scope"） |
| 真实 LLM 下 policy 消息是否真的影响模型行为 | **未验证**（所有测试用 `GenericFakeChatModel` 脚本化响应） |

**结论（口径 1 + 口径 4 + 口径 7）**：general 模式的"原生行为保持"在**架构层与自动化测试层**有充分证据；在**真实外部集成层**没有任何运行证据。这不是缺陷——TASK-001 的范围就是契约闭环——但不能据此声称"真实环境下已验证"。

---

## 6. knowledge 模式闭环

### 6.1 逐环明细

| 环 | 输入 | 输出 | 数据结构 | 实现文件 | 测试 | 限制 |
|---|---|---|---|---|---|---|
| ① 请求进入 | `config["context"]["rag_mode"]="knowledge"` | `runtime.context` 含该键 | `dict` | DeerFlow worker（未改动） | `test_05` | 必须显式传，无自动判定 |
| ② 账本分配 | `TaskInfo(run_id=...)` | `task_store` 中的 `RagTaskLedger` | `RagTaskLedger` | `lifecycle.py:18-24` | `test_04`（断言 `ledger["run_id"] == record.run_id`、`searches == 0`） | 依赖插件已注册 lifecycle |
| ③ 模式判定 + schema 保留 | `runtime.context` | 绑定含 `knowledge_search`；消息流注入 policy | `ModelRequest` | `middleware.py:87-99` | `test_02`、`test_knowledge_mode_keeps_tools_and_injects_policy_message` | policy 只是指令，不强制 |
| ④ 工具调用 | `query`、`metadata_filter?`、`temporal_constraint?` | `RetrievalRequest` | 7 字段冻结数据类 | `tools.py:78-86` | `test_retrieval_request_contract_shape` | `top_k` 被工具硬编码为 5，不接受外部传入 |
| ⑤ 检索 | `RetrievalRequest` | `RetrievalResponse`（3 条 Evidence） | 冻结契约 | `retrieval.py:63-105` | `test_stub_evidence_covers_full_contract_fieldset` | **Stub**：固定 3 条，无真实索引 |
| ⑥ 溯源打标 | Evidence + context 的 `run_id`/`thread_id` + `tool_call_id` | provenance 补齐的 Evidence | `Evidence` | `tools.py:53-55, 89-91` | `test_06`（断言 `provenance["run_id"] == record.run_id`） | 只在 context 里存在这些键时才打标 |
| ⑦ 入账 | Evidence 列表 | ledger entries（`validation_status="valid"`） | `EvidenceLedgerEntry` | `tools.py:93-101` + `ledger.py:35-58` | `test_04`（3 条、`tool_call_id == "c1"`、同一 `retrieval_run_id`） | 无去重，同一 run 多次搜索会重复入账 |
| ⑧ 返回信封 | `ToolResult` | JSON 字符串 → `ToolMessage` | `ToolResult` | `tools.py:103-111` | `test_06`、`test_07` | `artifact_refs` 恒为空列表 |
| ⑨ 收尾统计 | ledger + outcome | app 层累计 | `RagExtensionStats` | `lifecycle.py:26-34` + `ledger.py:79-86` | `test_lifecycle_allocates_ledger_and_absorbs_stats` | 内存态，进程重启即清零 |

### 6.2 闭环完整性

环 ①→⑨ 全部连通，且 `test_07_final_run_result_carries_stub_evidence` 验证了**最终 run 状态**（SSE 背后那份数据）里带着完整 evidence 信封与 run 级溯源。

**未闭环的部分**：最终答案是否真的引用了 evidence。policy 只是一条指令，模型可以无视。`test_07` 里的 `"Based on evidence [E1]"` 是**脚本化模型响应**，不是模型真实行为。强制引用属于 RagGuard，明确延期（口径 7）。

---

## 7. Evidence 契约（只记录代码中真实存在的字段）

来源：`rag-extension/rag_extension/contracts.py`。**不补充**架构文档中提到但未实现的字段。

### 7.1 类型别名

| 名称 | 取值 |
|---|---|
| `SourceType` | `"knowledge"` / `"document"` / `"mcp"` |
| `Authority` | `"HIGH"` / `"MEDIUM"` / `"LOW"` |
| `ValidationStatus` | `"valid"` / `"rejected"` |
| `STUB_PROFILE_VERSION` | `"stub-v0"` |

### 7.2 八类结构

| 结构 | 字段（按代码顺序） |
|---|---|
| `Evidence` | `evidence_id, content, title?, source_type, source_name, source_uri?, document_id?, external_id?, document_version?, source_revision?, index_version?, content_hash, retrieved_at, publish_time?, update_time?, authority（默认 MEDIUM）, provenance（默认 {}）, artifact_ref?` —— 共 18 字段 |
| `TemporalConstraint` | `before, after` + `from_dict()` / `to_dict()` |
| `RetrievalRequest` | `original_query, resolved_query, metadata_filter?, temporal_constraint?, top_k, profile_version, trace_id` —— 7 字段 |
| `RetrievalError` | `component, code, retryable, message` |
| `RetrievalTraceSummary` | `retrieval_run_id, variant_count, candidate_count, evidence_count, fastpass_hit, degraded, profile_version` —— 7 字段 |
| `RetrievalResponse` | `evidence: tuple[Evidence,...], trace, degraded, errors: tuple[RetrievalError,...] = ()` |
| `ToolError` | `code, message, retryable, component?` |
| `ToolResult` | `ok, data: RetrievalResponse\|None, error: ToolError\|None, trace_id, tool_call_id, artifact_refs: tuple = ()` |
| `EvidenceLedgerEntry` | `evidence, run_id, tool_call_id, retrieval_run_id?, validation_status, registered_at` |

另：`ToolResult` 的类注释写明 `ok=false` 时**永不携带** plausible evidence data（`data=None`），已由 `test_tool_result_envelope_consistency` 验证。

### 7.3 冻结语义（实测细节）

- 顶层 `frozen=True` 只阻止属性重绑定。代码在 `__post_init__` 里额外把嵌套容器**复制**并只读化：`dict` → `MappingProxyType(dict(value))`，`list`/`tuple` → `tuple(...)`。
- 每个结构**只冻结自己直接拥有的那一层**。`test_evidence_provenance_nested_filter_is_not_item_mutable` 之所以能通过，是因为传入的 `request.metadata_filter` **已经被 `RetrievalRequest` 自己冻结过**；若直接给 `Evidence` 传一个裸嵌套 dict，内层仍是普通可变 dict。
- `__getstate__` / `__setstate__` 处理 `MappingProxyType` 不可 pickle 的问题；`to_dict()` 是逃生口，用 `_plain()` 递归还原为可变容器。
- 已验证：不可变性（`test_evidence_contract_is_frozen`）、provenance 不可改（`test_evidence_provenance_is_not_item_mutable`）、evidence/errors 不可 append（`test_response_evidence_and_errors_are_not_appendable`）、artifact_refs 不可 append（`test_tool_result_artifact_refs_are_not_appendable`）、与调用方容器解耦（`test_contracts_detach_from_caller_supplied_containers`）、深拷贝与 pickle 存活（`test_frozen_contracts_survive_deepcopy_and_pickle`）。

---

## 8. 可观察性

### 8.1 三通道现状

| 通道 | 实现方 | 本次是否新增埋点 | 验证状态 |
|---|---|:--:|---|
| OTel / Monocle | DeerFlow 原生 | 否 | 口径 4，未针对 RAG 验证 |
| LangChain callbacks | LangChain 原生 | 否 | 口径 4 |
| RunJournal → RunEventStore | DeerFlow 后端专属 | **否** | 口径 1（已验证） |

### 8.2 从事件存储能读到什么

`test_rag_extension_trace.py` 用真实 `MemoryRunEventStore` 跑完整 `RunManager` + `run_agent`，**零 mock**，只读 DeerFlow 原本就记录的东西：

| 事件类型 | 能观察到 |
|---|---|
| `run.start` / `run.end` | 存在性；`run.end` 的 `metadata.status` |
| `run.error` | 非法 mode 导致的运行失败 |
| `llm.ai.response` | 模型是否被提供并请求了 `knowledge_search`（模式门控的间接证据） |
| `llm.tool.result` | **完整 Evidence 信封**，含 evidence_id 与 `provenance.run_id` / `provenance.thread_id` |

`test_run_events_are_scoped_per_run_on_a_shared_thread` 还验证了：同一 thread 上两次 run 的事件 `seq` 完全不相交，envelope 的 provenance 与产出它的 run 一一对应。

### 8.3 观察不到的东西（明确边界）

| 信息 | 为什么观察不到 |
|---|---|
| **注入的 policy SystemMessage（name=`rag_knowledge_policy`）** | 它是每次模型调用时**临时构造**的，`_prepare_model_request` 只 `request.override(messages=...)`，**从不写回 `messages` channel**。因此既不在事件存储里，也不在 checkpoint 状态里。 |
| 该消息的唯一可观察位置 | **仅运行期**，在交给模型的消息列表里。由 `test_rag_extension_gateway.py` 和 `test_knowledge_mode_keeps_tools_and_injects_policy_message` 断言。 |
| 为什么不能补 | `RunJournal` 没有通过 `deerflow_extension_api` 导出（只能从内部 `runtime.context["__run_journal"]` 取），且 `rag` 不在 `MIDDLEWARE_EVENT_TAGS` 里。需要 harness 侧支持。 |

这是**当前可观察性的最大缺口**：中间件的存在性可以间接推断（通过工具绑定），但中间件**实际注入了什么**不留痕。

### 8.4 HTTP / SSE 层

**未覆盖**。测试只到 run 级载荷，注释明确写 "HTTP/SSE over HTTP is still out of scope"。`GET /{thread_id}/runs/{run_id}/events` 这个 debug 端点本身是上游既有能力，本次未做端到端调用验证。

---

## 9. DeerFlow 原生能力保留情况

判定依据统一为：**TASK-001 的入库提交（`a0eead4e` / `a29a83be` / `602ecb82` / `848e1157` / `fdadff7b`）的 diff 是否触及该能力的代码**。

| 能力 | 代码位置 | 是否被触及 | 口径 | 备注 |
|---|---|:--:|---|---|
| 原生工具（Tool） | `packages/harness/deerflow/tools/` | 否 | 4 | 新增的 `knowledge_search` 是**追加**，不替换 |
| MCP | `packages/harness/deerflow/mcp/` | 否 | 4 | 目录存在（含 oauth、session_pool、interceptors），未改动 |
| Skills | `packages/harness/deerflow/skills/` | 否 | 4 | 目录存在（含 catalog、frontmatter、installer），未改动 |
| Sandbox | `packages/harness/deerflow/sandbox/` | 否 | 4 | `a29a83be` 只删了 Tenki provider 并更新两处 AGENTS.md 文档，未动 sandbox 核心 |
| Memory | `agents/middlewares/memory_middleware.py` | 否 | 4 | 未改动 |
| Checkpoint | LangGraph checkpointer | 否 | 4 | 测试用 `InMemorySaver` 验证过链路，但生产 checkpointer 未针对 RAG 验证 |
| SSE | `app/gateway/routers/` | 否 | 4 | 未改动；也未做端到端验证 |
| Trace（RunJournal → RunEventStore） | `runtime/events/` | 否 | 4 | RAG 只是**复用**既有埋点，未新增 instrumentation |
| Trace（OTel / Monocle） | 原生 | 否 | 4 | 未针对 RAG 验证 |

**统一结论（口径 4）**：九项原生能力全部为"沿用上游未改动"。但要注意——"未改动"不等于"已验证兼容"。只有 Tool 和 Trace（RunEventStore）有针对 RAG 场景的自动化测试证据（口径 1），其余七项属于口径 4。

---

## 10. 已实现 / 未实现边界表

### 10.1 已实现

| 能力 | 口径 | 关键证据 |
|---|---|---|
| 双模式显式解析与 fail-closed 校验 | 1 | `modes.py` + `test_rag_extension_modes.py`（14 例） |
| general 模式摘除 knowledge_search schema | 1 | `test_01`、`test_general_mode_hides_schema_and_blocks_smuggled_call` |
| general 模式拦截走私工具调用（同步 + 异步） | 1 | `test_wrap_tool_call_blocks_*`（4 例） |
| knowledge 模式注入 policy SystemMessage | 1 | `test_02`、`test_knowledge_mode_keeps_tools_and_injects_policy_message` |
| 工具层二次防御（无中间件时也拒绝） | 1 | `test_tool_defends_against_non_knowledge_mode_without_middleware` |
| 扩展未启用时完全退化为原生 | 1 | `test_08`、`test_extension_disabled_leaves_no_knowledge_evidence_in_run_events` |
| 插件/中间件耦合自检 | 1 | `test_middleware_fails_closed_when_plugin_not_loaded` |
| Evidence 契约结构与深冻结 | 1 | `test_rag_extension_contracts.py`（18 例） |
| run 作用域证据账本 + app 层统计 | 1 | `test_plugin.py`（3 例）+ `test_04` |
| 证据信封携带 run/thread/tool_call 溯源 | 1 | `test_06`、`test_07` |
| 最终 run 状态携带证据（SSE 载荷） | 1 | `test_07` |
| Trace 可观察（模式门控 + 证据 + 结局） | 1 | `test_rag_extension_trace.py`（5 例） |
| 每次检索产生独立 `retrieval_run_id` | 1 | `test_04`（三次条目同一 retrieval_run_id）；`uuid4()` 实现 |
| `metadata_filter` / `temporal_constraint` 参数通路 | 1 | `test_temporal_constraint_round_trips`、`test_retrieval_request_metadata_filter_is_read_only` |
| 契约与调用方容器解耦 | 1 | `test_contracts_detach_from_caller_supplied_containers` |
| 契约可 pickle / deepcopy | 1 | `test_frozen_contracts_survive_deepcopy_and_pickle` |

### 10.2 未实现

| 能力 | 口径 | 证据 / 说明 |
|---|---|---|
| 真实检索（BM25 / 向量 / 外部知识库） | 6 | `retrieval.py` 全文 105 行，3 条硬编码文档，无任何索引或外部调用 |
| 自动模式判定（auto / router） | 6 | `RAG_MODES` 只有两值；全仓无路由逻辑 |
| Gateway 层 `rag_mode` 校验 / HTTP 422 | 6 | `backend/app/` grep `rag_mode` 零命中 |
| 最终答案引用证据的强制校验（RagGuard） | 7 | `middleware.py` 文件头注释明说"这是指令不是约束，强制引用归 RagGuard，已延期" |
| policy SystemMessage 的持久化 / Trace 记录 | 6 | 从不写回 `messages` channel（§8.3） |
| Evidence 去重 | 6 | `ledger.register_evidence` 无条件 `extend`，同 run 多次搜索会重复 |
| `top_k` 外部可调 | 6 | `tools.py` 硬编码 `_STUB_TOP_K = 5` |
| `artifact_refs` 实际使用 | 6 | 恒为 `[]` |
| `publish_time` / `update_time` 时间过滤 | 6 | 字段存在，但 Stub 不填（None），检索也不按时间过滤 |
| `authority` 分级生效 | 6 | 字段存在，Stub 统一写 `"MEDIUM"`，无任何消费方 |
| `degraded` / `errors` 真实降级路径 | 6 | Stub 恒 `degraded=False`、`errors=[]`，无降级逻辑 |
| 文档来源（document / mcp） | 6 | `SourceType` 定义了三值，Stub 只产 `"knowledge"` |
| app 层统计持久化 | 6 | `RagExtensionStats` 是内存态，进程重启清零 |
| 真实 MCP / Skill / Sandbox 集成验证 | 6 | 所有测试用 1 行桩工具（§5.3） |
| HTTP / SSE 端到端验证 | 7 | TASK-001 §7.2 明确排除 |

---

## 11. 验证证据索引

每个"已实现并验证"的结论都绑定下列证据之一：**实现文件 / 测试文件 / 测试结果 / 配置接线 / Git 提交**。

### 11.1 测试文件与用例数

| 测试文件 | 行数 | 用例 | 恢复/重建 | Git 提交 |
|---|---:|---:|---|---|
| `backend/tests/test_rag_extension_gateway.py` | 408 | 8 | 原样恢复 | `602ecb82` |
| `backend/tests/test_rag_extension_trace.py` | 274 | 5 | 原样恢复 | `848e1157` |
| `backend/tests/test_rag_extension_contracts.py` | 375 | 18 | 原样恢复 | `848e1157` |
| `backend/tests/test_rag_extension_integration.py` | 194 | 4 | 原样恢复 | `848e1157` |
| `backend/tests/test_rag_extension_middleware.py` | 197 | 13 | 原样恢复 | `848e1157` |
| `backend/tests/test_rag_extension_modes.py` | 105 | 14 | **重建** | `fdadff7b` |
| `rag-extension/tests/test_plugin.py` | 142 | 6 | 原样 | `d034a3a` |
| `rag-extension/tests/test_entry_point.py` | 11 | 1 | 原样 | `d034a3a` |

### 11.2 实测结果（2026-08-30 本机）

| 范围 | 收集 | 通过 | 失败 | 耗时 |
|---|---:|---:|---:|---:|
| modes 单文件 | 14 | 14 | 0 | 3.47s |
| 六个 RAG 测试文件 | 62 | **62** | 0 | 9.01s |
| rag-extension 包内 | 7 | 7 | 0 | 1.03s |
| Gateway 回归（`test_gateway_services`） | 138 | 138 | 0 | 7.05s |
| 后端定向子集 | 183 | 182 | 1（**环境问题**） | 12.95s |
| 综合定向回归 | 311 | 311 | 0 | 5.67s |

**唯一失败项归因（已钉死）**：`test_config_version.py::test_version_26_config_upgrades_to_checkpoint_channel_mode`。根因是沙箱把 `wsl.exe` 列入黑名单，且黑名单提示是 GBK 编码中文，`text=True` 按 UTF-8 解码抛 `UnicodeDecodeError`，导致 `result.stderr` 变 `None`。**与 RAG 无关，非代码问题**。

**判定方式提醒**：pytest 的临时目录清理会触发沙箱批量删除守卫，导致 exit code 非 0。判定是否通过要看 stdout 的统计行，不要看 exit code。

**本文定稿时复跑确认**：`62 passed in 2.47s`（六个 RAG 文件，exit 0）。耗时低于上表是缓存预热差异，用例数一致。

### 11.3 变异测试（证伪首次全绿）

对已通过测试做定向变异，确认测试真的能失败：

| # | 变异 | 实测失败 | 对照 |
|---|---|---|---|
| A | gateway 丢弃 middlewares | 5 failed / 3 passed（02/03/04/06/07） | 与 skill 记录参考值逐字一致 |
| B | gateway 强转 knowledge | 3 failed / 5 passed（01/03/05） | 与 skill 记录参考值逐字一致 |
| C | modes 失效开放 | 5 failed / 9 passed（5 个 fail-closed 用例） | 本次新增参考值 |
| D | modes 默认翻转 | 2 failed / 12 passed（2 个默认解析用例） | 本次新增参考值 |

安全做法：非 editable 安装下，变异只打 `.venv` 已安装副本，**完全不碰 `rag-extension` 源码仓库**。还原后 sha256 复验与变异前一致（`70fcbda2734b140d8d70a481e97574b057193ace6cde0a2419db5a80d519bff2`），重跑仍是 62 passed。

### 11.4 配置接线证据

| 项 | 位置 |
|---|---|
| 中间件声明 | `deer-flow/config.yaml:1582-1584` |
| 插件声明 | `deer-flow/config.yaml:1586-1592`（`enabled: true`、`required: true`） |
| 依赖声明 | `deer-flow/backend/pyproject.toml:58`、`:114` |
| 锁文件条目 | `deer-flow/backend/uv.lock:914`、`:4091-4093` |
| Entry point | `rag-extension/pyproject.toml` 的 `[project.entry-points."deerflow.extensions"]` |
| 快照忽略规则 | `deer-flow/.gitignore` 末尾 `# Extension Manager install snapshots` 段 |

### 11.5 Git 提交证据

| 提交 | 仓库 | 内容 |
|---|---|---|
| `d034a3a` | rag-extension | 骨架入库（阶段 0-1 产物） |
| `a29a83be` | deer-flow | 删除 Tenki provider（10 files, +4 / -2047） |
| `a0eead4e` | deer-flow | 注册 RAG extension 快照（`.gitignore` / `pyproject.toml` / `uv.lock`） |
| `602ecb82` | deer-flow | 恢复 gateway 测试（408 行 / 8 例） |
| `848e1157` | deer-flow | 恢复 trace / contracts / integration / middleware（40 例） |
| `fdadff7b` | deer-flow | 重建 modes 测试（14 例），docstring 首行标注 `REBUILT 2026-08-30 -- NOT a verbatim recovery` |

### 11.6 静态检查

- `uv run ruff check` + `ruff format --check`：rag-extension 包内通过。
- 生产代码零改动原则：本轮未为满足测试修改任何生产代码。

---

## 12. 完成标准自检

| # | 标准 | 结果 |
|---|---|:--:|
| 1 | 每个结论都能归到 7 种口径之一，无"支持/完成"等无界定词 | ✅ |
| 2 | 8 个模块逐一核对，记录职责 / 是否生产实现 / 测试证据 | ✅ §2 |
| 3 | 扩展加载方式 7 项全部核对，含"接线不入库"这一风险 | ✅ §3 |
| 4 | 请求与模式链路 7 问全部有代码级答案 | ✅ §4 |
| 5 | general 模式严格区分"架构未改 / 有自动化回归 / 真实运行验证"，第三层如实标为未做 | ✅ §5 |
| 6 | knowledge 闭环 9 环逐环标明输入 / 输出 / 结构 / 文件 / 测试 / 限制 | ✅ §6 |
| 7 | Evidence 契约只记录代码真实字段，不补充架构文档未实现字段 | ✅ §7 |
| 8 | 可观察性明确写出"什么能读到 / 什么读不到 / 为什么" | ✅ §8 |
| 9 | 原生能力 9 项逐一核对，判定依据统一为提交 diff | ✅ §9 |
| 10 | 已实现 / 未实现边界表，未实现项给出口径与证据 | ✅ §10 |
| 11 | 每条"已实现并验证"绑定至少一种证据（文件 / 测试 / 结果 / 配置 / 提交） | ✅ §11 |
| 12 | 未引用 TASK-001 文字描述作为唯一依据 | ✅ 全文证据均为代码行、测试结果或提交 diff |

---

## 附：待决项

| # | 发现 | 状态 | 建议 |
|---|---|:--:|---|
| 1 | `README.md:56` 声称"HTTP 422 at run boundary"，代码里没有 422 逻辑 | ⏳ | 修正 README 措辞为"运行期 fail-closed，run 失败" |
| 2 | RAG 运行时接线只存在于 gitignored 的 `config.yaml`，`config.example.yaml` 无对应块 | ⏳ | 决定是否给 `config.example.yaml` 加注释块，或在部署文档写明手工步骤 |
| 3 | `backend/extensions/sources/.rag-extension.remove-3ubzl2z9/` 残留目录 | ✅ **已清理** | 见 §1.4 |
| 4 | `myAgent/` 根目录不是 git 仓库，`docs/` 无版本控制 | ⏳ | 决定建库形式（独立仓库 vs 整体仓库） |
| 5 | 干净 clone → `make extension-install` → `uv sync` 的重建路径未实测 | ⏳ | 建议单开任务验证 |

另：**干净 clone → `make extension-install` → `uv sync` 的重建路径本次未实测**（只在既有环境跑过 `uv lock --check`）。口径 3，建议单开任务验证。

---
---
# 第二部分：当前实际架构（As-Is Architecture）

本部分只画**已经落地的结构**。任何未实现的组件一律放在 §21 的独立清单里，用「未实现」标注，**不接入主链**。

原架构设计见 `docs/architecture/01-system-design.md`（Agentic RAG 系统总体设计 v1.1）。与它的差距对照见 §22。

**引用约定**：本部分中「原设计 §N」一律指上述架构文档的章节；「§N」无前缀时指本文。

---

## 13. 架构边界

```text
DeerFlow Host
└── RAG Extension（插件）
```

**边界的四条硬约束（均可验证）**：

| # | 约束 | 验证方式 |
|---|---|:--|
| 1 | DeerFlow 继续拥有 Agent Runtime | `backend/app/` 与 `backend/packages/` 中 `rag_mode` grep 零命中；Agent Graph 构建未被替换 |
| 2 | RAG Extension 是插件，**不是独立服务** | 无独立进程、无端口、无 HTTP 接口；`rag-extension/` 只有 8 个 `.py`，无 server 代码 |
| 3 | **不存在**第二套 Gateway / Agent / Checkpoint / SSE / MCP Runtime | TASK-001 入库生产改动仅 3 个文件（§1.2），无一份属于上述子系统 |
| 4 | **没有**独立检索服务与检索数据库 | `retrieval.py` 全文 105 行、3 条硬编码文档；全仓无 BM25 / 向量库 / 数据库连接代码 |

**同进程部署**：RAG Extension 以 Python 包形式装进 `backend/.venv`，与 DeerFlow 同进程运行。这一点与原设计 §12「RetrievalService 与 RAG Extension 同进程部署」一致。

---

## 14. 组件关系图（As-Is）

```text
                              Client
                                │
                                ▼
                    ┌───────────────────────┐
                    │   DeerFlow Gateway    │  ← DeerFlow 所有
                    │  (HTTP / SSE 接入)    │
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │ DeerFlow RunManager   │  ← DeerFlow 所有
                    │   / Agent Runtime     │
                    │  (Graph + Checkpoint) │
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │ KnowledgeModeMiddleware│ ← RAG Extension 所有
                    │  (模式门控 / 消息注入) │    operator-trusted 装配
                    └─────┬───────────┬─────┘
                          │           │
              ┌───────────┘           └───────────┐
              ▼                                   ▼
   ┌───────────────────┐             ┌───────────────────────┐
   │  general（缺省）   │             │     knowledge         │
   │                   │             │                       │
   │ knowledge_search  │             │ ┌───────────────────┐ │
   │   schema 已摘除   │             │ │ 注入 Knowledge    │ │
   │   （模型看不到）  │             │ │ Policy SystemMsg  │ │
   │                   │             │ └───────────────────┘ │
   ├───────────────────┤             ├───────────────────────┤
   │ DeerFlow Native   │             │ DeerFlow Native       │
   │ Tools / MCP /     │             │ Tools / MCP / Skills  │
   │ Skills（不变）    │             │ （不变）              │
   └─────────┬─────────┘             ├───────────────────────┤
             │                       │ + knowledge_search    │
             │                       └───────────┬───────────┘
             │                                   ▼
             │                       ┌───────────────────────┐
             │                       │    Stub Retrieval     │ ← RAG Extension
             │                       │  (retrieval.py, 固定) │
             │                       └───────────┬───────────┘
             │                                   ▼
             │                       ┌───────────────────────┐
             │                       │  Evidence（冻结契约） │ ← RAG Extension
             │                       │  contracts.py         │
             │                       └───────────┬───────────┘
             │                                   ▼
             │                       ┌───────────────────────┐
             │                       │   Temporary Ledger    │ ← RAG Extension
             │                       │  (run 作用域，内存)   │
             │                       └───────────┬───────────┘
             │                                   ▼
             ▼                                   ▼
   ┌─────────────────────────────────────────────────────┐
   │              Agent Response（由 LLM 生成）          │ ← DeerFlow 所有
   └─────────────────────────┬───────────────────────────┘
                             ▼
   ┌─────────────────────────────────────────────────────┐
   │  DeerFlow Run Events / Trace / SSE（原生，未改动）   │ ← DeerFlow 所有
   └─────────────────────────────────────────────────────┘
```

**读图要点**：

- RAG Extension 在整张图里只占**四条竖线**：中间件、工具、检索、账本。
- 上下两条横带（Gateway、Run Events）**完全是 DeerFlow 原生**，Extension 只复用不接管。
- general 分支上没有任何 RAG 组件生效 —— 这正是「原生行为保持」的结构性体现。
- 从 `knowledge_search` 到 `Evidence` 到 `Ledger` 是**串行且必然**的；但**是否进入这条链路由 LLM 决定**（见 §16）。

---

## 15. 组件所有权

| 组件 | 所有者 | 代码位置 |
|---|---|---|
| Gateway（HTTP / SSE 接入） | **DeerFlow** | `backend/app/gateway/` |
| Agent Runtime（Graph、模型调用） | **DeerFlow** | `backend/packages/harness/deerflow/agents/` |
| Tool Runtime（工具执行） | **DeerFlow** | LangGraph `ToolNode` + `packages/harness/deerflow/tools/` |
| MCP Runtime（Server 管理 / Tool Discovery） | **DeerFlow** | `packages/harness/deerflow/mcp/` |
| Skill Runtime（激活 / Tool Policy） | **DeerFlow** | `packages/harness/deerflow/skills/` |
| Checkpoint（Thread / Run 状态） | **DeerFlow** | LangGraph checkpointer |
| SSE（流式输出） | **DeerFlow** | `app/gateway/routers/` |
| Trace（RunJournal / RunEventStore） | **DeerFlow** | `backend/packages/.../runtime/events/` |
| Subagent / Sandbox | **DeerFlow** | `packages/harness/deerflow/sandbox/` |
| — | — | — |
| 模式控制（解析 + 门控） | **RAG Extension** | `rag_extension/modes.py` + `middleware.py` |
| `knowledge_search` 工具 | **RAG Extension** | `rag_extension/tools.py` |
| Stub Retrieval | **RAG Extension** | `rag_extension/retrieval.py` |
| Evidence 契约 | **RAG Extension** | `rag_extension/contracts.py` |
| 临时 Ledger | **RAG Extension** | `rag_extension/ledger.py` + `lifecycle.py` |

**避免的误解**：Extension **没有**接管任何一项 DeerFlow 能力。它只往 Agent 栈里**追加**了一个中间件和一个工具，其余全部复用宿主实现。原设计 §3 也要求「不在 DeerFlow Core 内复制实现」，当前实现满足该约束。

---

## 16. 三条模式时序

### 16.1 general 模式（缺省）

```text
Request(rag_mode=general 或 不传 rag_mode)
    │
    ▼
DeerFlow Gateway
    │
    ▼
DeerFlow Agent Runtime
    │
    ▼
KnowledgeModeMiddleware._prepare_model_request
    │  resolve_rag_mode(context) → "general"
    │  → request.override(tools=[去掉 knowledge_search])
    ▼
模型绑定中不存在 knowledge_search
    │
    ▼
DeerFlow Native Tool / MCP / Skill（原生链路，未被替换）
    │
    ▼
Answer
```

**四条必须标注的性质**：

| 性质 | 说明 | 证据 |
|---|---|---|
| `general` 是**缺省模式** | 缺失 / 空 context / 无键 / 值为 `None` 四种情况都解析为 general | `modes.py::resolve_rag_mode`；`test_rag_extension_modes.py` 前 4 例 |
| **不自动判断**是否进入知识检索 | 代码中不存在任何 auto / 路由 / 意图判定逻辑 | `RAG_MODES` 只有两值；全仓无 router |
| **不产生** RAG Evidence | 工具在 general 下直接返回错误信封；即使绕过中间件，工具自身也拒绝 | `test_tool_defends_against_non_knowledge_mode_without_middleware` |
| 原生运行链路**不被替换** | 只是从绑定列表里删掉 Extension 自己加的那一个工具 | `test_01` 断言 `bound[0] == ["native_tool"]` |

另有一道**第二防线**：即便模型设法发起了 `knowledge_search` 调用（走私），`_blocked_tool_message` 会拦截并回一条 `status="error"` 的 ToolMessage，同步/异步两条路径都拦（4 个用例）。

### 16.2 knowledge 模式

```text
Request(rag_mode=knowledge)
    │
    ▼
DeerFlow Gateway
    │
    ▼
DeerFlow Agent Runtime
    │
    ▼
RagTaskLifecycle.on_task_start  → 分配 RagTaskLedger(run_id)
    │
    ▼
KnowledgeModeMiddleware
    ├── 注入 Knowledge Policy SystemMessage（插在前导 SystemMessage 之后）
    └── 保留 knowledge_search schema（模型可见）
             │
             ▼  ← 【LLM 自行决定是否调用，不是固定两步 RAG】
        knowledge_search(query, metadata_filter?, temporal_constraint?)
             │
             ▼
        Stub Retrieval（3 条固定 Evidence）
             │
             ▼
        RetrievalResponse → Tool Result Envelope（JSON 字符串）
             │
             ▼
        Evidence（打上 run_id / thread_id / tool_call_id 溯源）
             │
             ▼
        Temporary Ledger（register_evidence，validation_status="valid"）
             │
             ▼
        Agent 生成回答（Policy 只是指令，不强制引用）
             │
             ▼
        RagTaskLifecycle.on_task_stop → 回收 ledger，absorb 到 app 层统计
```

**关键标注：当前不是固定两步 RAG Pipeline。**

- 是否调用 `knowledge_search`、调用几次、是否追加调用，**完全由 Agent / LLM 决定**。
- 原设计 §8 的序列里有 `evaluate sufficiency` → `sufficient / search_again / abstain` 三分支控制流。**当前实现没有这个分支**——没有 `EvidenceSufficiencyService`，没有补搜循环，没有拒答判定。
- 因此测试里的「调一次工具然后回答」是**脚本化模型响应**（`GenericFakeChatModel`），不是系统强制的行为。真实 LLM 可能不调工具、也可能调十次。

### 16.3 非法模式

```text
Request(rag_mode=invalid，例如 "auto" / "" / "Knowledge" / " knowledge" / 非字符串)
    │
    ▼
DeerFlow Gateway（不认识 rag_mode，不做任何校验）
    │
    ▼
DeerFlow Agent Runtime
    │
    ▼
KnowledgeModeMiddleware._prepare_model_request
    │  resolve_rag_mode() → raise RagModeError
    │    code="invalid_rag_mode"，携带 value 与 expected
    ▼
Fail Closed
    │
    ▼
模型未调用、工具未执行
    │  record.status = RunStatus.error
    │  record.error 含 "invalid rag_mode"
    ▼
run.error 事件写入 RunEventStore
```

**非法值绝不会**：

| 不会发生的回退 | 证据 |
|---|---|
| 回退为 general | `test_03` 断言 `result.record.status is RunStatus.error` |
| 自动切换 knowledge | 同上；`bound == []` 证明从未绑定工具 |
| 启动模型调用 | `test_03` 断言 `result.bound == []`、`result.messages == []` |

**失败位置澄清**：这是**运行期**失败，发生在中间件内部，不是 HTTP 边界。Gateway 层根本不认识 `rag_mode`（全仓 grep 零命中），因此**不会**返回 422。客户端看到的是 run 失败。（`README.md:56` 关于 422 的描述与代码不符，见附录待决项 1。）

---

## 17. Evidence 数据流

```text
  RetrievalRequest                      实现：contracts.py（7 字段冻结数据类）
        │                              构造：tools.py:78-86
        ▼
  Stub Retriever                        实现：retrieval.py::StubRetrievalService.retrieve
        │                              生成 retrieval_run_id = uuid4().hex
        │                              content_hash = sha256(content)
        ▼
  RetrievalResponse                     实现：contracts.py
        ├── Evidence[]                  evidence / trace / degraded / errors
        └── RetrievalError[]            当前恒为 () —— Stub 无错误路径
        │
        ▼
  溯源打标                              实现：tools.py::_stamp_run_provenance
        │                              合入 context 的 run_id / thread_id + tool_call_id
        ▼
  Tool Result Envelope                  实现：contracts.py::ToolResult
        │                              序列化：tools.py::_envelope_json → json.dumps(to_dict())
        ▼
  ToolMessage                           由 LangGraph ToolNode 包装
        │                              内容是上面的 JSON 字符串
        ▼
  Ledger Entry                          实现：ledger.py::RagTaskLedger.register_evidence
        │                              contracts.py::EvidenceLedgerEntry
        │                              validation_status="valid"
        ▼
  ┌─────────────────┬──────────────────────────────┐
  ▼                 ▼                              ▼
Run Event        Agent Context            App 层统计
(llm.tool.result) (下一轮模型可见)        (RagExtensionStats)
                                          实现：ledger.py::absorb
```

**每个节点的实现模块都已在图上标出，不是概念名。**

**关于 Artifact**：契约里有 `artifact_ref` 字段、`ToolResult.artifact_refs`，但 Stub 恒为空。原设计 §6 的 `document_read` 会把完整正文存为 Artifact —— **该工具未实现**，当前没有任何 Artifact 产出。

---

## 18. Trace 与持久化边界

### 18.1 三类数据的分界

| 类别 | 内容 | 存在哪 | 生命周期 |
|---|---|---|---|
| **Agent 消息状态** | HumanMessage / AIMessage / ToolMessage | Checkpoint（DeerFlow） | 跨 run 持久（按 thread_id） |
| **Tool / Evidence 数据** | Evidence 信封（JSON 字符串，嵌在 ToolMessage.content 里） | **随消息状态一起进 Checkpoint** | 同上 |
| **Run Event / Trace 数据** | `run.start` / `llm.ai.response` / `llm.tool.result` / `run.end` / `run.error` | RunEventStore（DeerFlow 原生） | 按 run 隔离 |

关键点：**Evidence 没有独立存储**。它以 JSON 字符串形式躺在 ToolMessage 的 `content` 里，因此天然随 Checkpoint 持久化，也天然被 Trace 记录。

### 18.2 Evidence 如何进入 ToolMessage

`knowledge_search` 返回的是**字符串**（`_envelope_json()` 的结果），LangGraph 的 ToolNode 把它包成 `ToolMessage(content=<JSON 字符串>, name="knowledge_search")`。

- 因此 `llm.tool.result` 事件里存的是**完整的 Evidence 信封**（`test_knowledge_mode_evidence_is_observable_in_run_events` 直接 `json.loads` 它）。
- 也因此在 `final_values`（SSE 背后那份数据）里能取到 evidence_id 与 provenance（`test_07`）。

### 18.3 什么进入 Run Event Store

| 事件 | 是否有针对 RAG 的内容 | 说明 |
|---|:--:|---|
| `run.start` / `run.end` | 否 | 原生事件，Extension 未新增 |
| `run.error` | 是（间接） | 非法 mode 导致的失败会落在这里 |
| `llm.ai.response` | 是（间接） | 记录模型请求了哪些工具 → 可反推模式门控是否生效 |
| `llm.tool.result` | **是（直接）** | 完整 Evidence 信封 |

**Extension 没有创建任何独立 Trace 系统。** 全部复用 DeerFlow 原生埋点，零新增 instrumentation。原设计 §3 列出的「RAG Trace」属于 Extension 职责，**当前未实现**。

### 18.4 什么通过现有 SSE 输出

**未做端到端验证**。测试只验证到 run 级载荷（即 SSE 会发布的那些数据），未真实发起 HTTP/SSE 请求。这是 §10 里标注的「不在当前范围」项。

### 18.5 Policy SystemMessage 的存活范围

```text
_prepare_model_request()
    │
    ├── 构造 SystemMessage(name="rag_knowledge_policy")
    ├── _insert_after_leading_system_messages()  插到连续前导 SystemMessage 之后
    └── request.override(messages=messages)      ← 只进模型调用，不写回消息 channel
```

| 问题 | 答案 |
|---|---|
| 是否进入持久化消息？ | **否**。从不写回 `messages` channel |
| 是否在 Checkpoint 里？ | **否** |
| 是否在 Run Event Store 里？ | **否** |
| 只在什么时候存在？ | **仅模型调用期间**，在交给模型的消息列表里 |
| 怎么验证？ | `test_rag_extension_gateway.py` 与 `test_knowledge_mode_keeps_tools_and_injects_policy_message` 从 `seen_messages` 里断言 |
| 为什么不能补？ | `RunJournal` 未通过 `deerflow_extension_api` 导出（只能走内部 `runtime.context["__run_journal"]`，明确禁用）；`rag` 不在 `MIDDLEWARE_EVENT_TAGS` 里。需要 harness 侧支持 |

**这是当前可观察性的最大缺口**：中间件注入了什么，事后无痕。

---

## 19. 安装与运行关系

```text
  rag-extension/  （独立 Git 仓库，HEAD d034a3a）
  ┌──────────────────────────────────────────────┐
  │  ★ 权威源码 —— 唯一允许手工编辑的地方          │
  └────────────────────┬─────────────────────────┘
                       │
                       │  make extension-install SOURCE=../rag-extension
                       │  （复制，非 editable）
                       ▼
  deer-flow/backend/extensions/sources/rag-extension/
  ┌──────────────────────────────────────────────┐
  │  安装快照 —— 由 install 重新生成，禁止就地改   │
  │  被 .gitignore:75-77 排除，不入库             │
  └────────────────────┬─────────────────────────┘
                       │
                       │  uv 安装（非 editable）
                       ▼
  deer-flow/backend/.venv/Lib/site-packages/rag_extension/
  ┌──────────────────────────────────────────────┐
  │  ★ 实际运行副本 —— 测试导入的就是这一份        │
  └────────────────────┬─────────────────────────┘
                       │
                       │  config.yaml 的 plugins: 块
                       │  （该文件 gitignored，接线不入库）
                       ▼
  DeerFlow Plugin Loader
      → 加载 entry point rag_extension:install
      → 注册 RagTaskLifecycle
                       │
                       │  config.yaml 的 extensions.middlewares: 块
                       ▼
  KnowledgeModeMiddleware 装配进 Agent 栈
      （operator-trusted，因为需要 request.override 能力）
```

**四条必须记住的规则**：

| # | 规则 | 后果 |
|---|---|---|
| 1 | 独立仓库是**权威源码** | 改代码只改 `rag-extension/` |
| 2 | `backend/extensions/` 是**安装快照** | 改了会被下次 install 覆盖，且它不入库 |
| 3 | `.venv` 是**实际运行副本** | 测试导入的是它，不是源码 |
| 4 | 改权威源码**不会**自动更新运行副本 | **必须重新执行 `make extension-install`**，否则测试仍跑旧代码 |

当前状态（已实测）：三份副本的 8 个模块**逐字节相同**。

**这个结构的两个副作用**：

- **变异测试可以完全隔离**：改 `.venv` 副本做实验，一点不碰 git 仓库，验证完按字节还原即可。
- **干净 clone 不能直接 `uv sync --locked`**：`pyproject.toml:114` 与 `uv.lock:4091` 都指向被 gitignore 的 `extensions/sources/rag-extension`。推断顺序是先 `make extension-install` 再 sync，**该路径未实测**（口径 3）。

---

## 20. 原生能力的复用标记

下表标记的是「**复用宿主实现**」，不是「Extension 重新实现了一遍」。

| 能力 | 状态 | 说明 |
|---|---|---|
| 原生 Tool | **复用** | `knowledge_search` 是**追加**，不替换任何一个原生工具 |
| MCP Runtime | **复用** | `packages/harness/deerflow/mcp/` 零改动；Extension 不改写 MCP Client（符合原设计 §4 禁令） |
| Skill Runtime | **复用** | `packages/harness/deerflow/skills/` 零改动 |
| Subagent / Sandbox | **复用** | 零改动 |
| Checkpoint | **复用** | Evidence 搭 ToolMessage 的便车进 Checkpoint，Extension 无独立存储 |
| SSE | **复用** | 零改动 |
| Trace | **复用** | 零新增埋点，完全读宿主已有的 `llm.tool.result` 等事件 |
| Memory | **复用** | `memory_middleware.py` 零改动 |

原设计 §4 明确禁止「RAG Extension 改写 DeerFlow MCP Client」——当前实现满足。

---

## 21. 尚不存在的组件（未实现清单）

以下组件**不接入上面任何一张图**。列出是为了防止读者误以为它们已经存在。

### 21.1 检索链路

| 组件 | 状态 | 原设计出处 |
|---|:--:|---|
| BM25 | **未实现** | 原设计 §8 序列 `BM25 / Vector / document metadata` |
| Vector DB | **未实现** | 同上 |
| KG（知识图谱） | **未实现** | 原设计 §14 扩展点 |
| RRF（融合） | **未实现** | 原设计 §8 `expansion / fusion / quality pipeline` |
| Reranker | **未实现** | 原设计 §9 Model Roles |
| Query Expansion | **未实现** | 原设计 §8 `expansion` |
| LLM Grading | **未实现** | 原设计 §9 Model Roles |

### 21.2 存储与基础设施

| 组件 | 状态 |
|---|:--:|
| PostgreSQL | **未接入** |
| OpenSearch | **未接入** |
| 任何检索数据库 | **未接入** |
| 独立检索服务 | **未实现**（当前同进程 Stub） |

### 21.3 RAG 应用层

| 组件 | 状态 | 原设计出处 |
|---|:--:|---|
| `EvidenceSufficiencyService` | **未实现** | 原设计 §8 `evaluate sufficiency` 分支 |
| Agent 多轮补搜循环 | **未实现** | 原设计 §8 `search_again` 分支 |
| RagGuard / RagGuardMiddleware | **未实现** | 原设计 §3、§7、§13 |
| CitationService | **未实现** | 原设计 §3、§7 |
| Abstention（拒答） | **未实现** | 原设计 §8 `abstain` 分支 |
| RAG Trace | **未实现** | 原设计 §3、§7 `RetrievalTraceRecorder` |
| `document_read` | **未实现** | 原设计 §6 |
| `wikipedia_search` / `wikipedia_read` | **未实现** | 原设计 §6 |
| `ExternalEvidenceService` | **未实现** | 原设计 §6、§7 |
| MCP 外部证据（Evidence 型 MCP 适配） | **未实现** | 原设计 §3、09 号文档 |
| `knowledge-research` Skill | **未实现** | 原设计 §6 |
| 权限治理 | **未实现**（原设计即已延期） | 原设计 §13 |

### 21.4 一句话总结当前定位

```text
当前 = 契约形状正确的 Stub 闭环
     = 「证明接口设计可行」的最小验证
     ≠ 完整 Agentic RAG 系统
```

**当前系统能做到**：显式模式切换、工具可见性门控、Evidence 契约端到端贯通、证据可溯源到 run/tool-call、Trace 可观察。

**当前系统做不到**：真实检索、质量排序、证据充分性判断、补搜循环、引用强制校验、拒答。

---

## 22. 与原架构设计的差距对照

对照基准：`docs/architecture/01-system-design.md`（Agentic RAG 系统总体设计 v1.1）。

| 原设计能力 | 当前状态 | 差距 |
|---|---|---|
| 扩展式接入 DeerFlow | **已完成** | 无。插件 + operator-trusted 中间件双通道装配，未侵入 Core |
| 显式模式控制 | **已完成** | 无。`general` / `knowledge` 两值，fail-closed，无 auto（与原设计 §5「V1 不实现 auto」一致） |
| Evidence 标准化 | **基础契约完成** | 尚无真实检索。8 类契约结构 + 深冻结已落地，但数据全部来自 Stub |
| ModePolicy | **已完成** | 无（实现为 `modes.py` + `middleware.py`） |
| RagToolFacade | **部分完成** | 4 个工具只实现 `knowledge_search`；`document_read` / `wikipedia_*` 未实现 |
| RetrievalService | **接口形状完成，实现为 Stub** | 无真实检索器；`StubRetrievalService` 符合接口形状但返回固定值 |
| EvidenceLedger | **基础完成** | run 作用域内存账本，无持久化、无去重；原设计的跨 run 归因未实现 |
| 请求模式约束 | **已完成** | 无 |
| 复合检索 | **未实现** | 后续任务。BM25 / Vector / KG / RRF / Reranker 全部缺失 |
| Agent 多轮补搜 | **未实现** | 后续任务。无 `EvidenceSufficiencyService`，无 sufficiency 分支 |
| MCP 外部证据 | **未实现** | 后续任务。无 `ExternalEvidenceService`，无 Evidence 型 MCP 适配 |
| RagGuard（最终 grounding 校验） | **未实现** | 后续任务。Policy 只是指令，模型可无视 |
| CitationService | **未实现** | 后续任务。契约里有字段，无消费方 |
| Abstention（无证据拒答） | **未实现** | 后续任务 |
| RAG Trace | **未实现** | 后续任务。当前只能从宿主 `llm.tool.result` 间接读到信封 |
| Model Roles（8 个可配置角色） | **未实现** | 后续任务。当前只有单一 Agent Model，无任何角色配置 |
| 数据与状态归属（原设计 §10） | **部分完成** | Evidence 的存储借用宿主 Checkpoint，无独立设计落地 |
| 可靠性与安全边界（原设计 §13） | **部分完成** | 做到了「外部正文按 Data 处理」与「失败 fail-closed」；其余（严格模式 RagGuard、无证据拒答、局部降级）未实现 |

### 22.1 一句话总结

原设计 §7 的组件树列出 **10 个顶层组件**（其中 `RagToolFacade` 下挂 4 个工具）。逐个清点：

| 落地程度 | 数量 | 组件 |
|---|:--:|---|
| 完全落地 | **2** | `ModePolicy`、`EvidenceLedger`（基础版） |
| 部分落地 | **2** | `RagToolFacade`（4 个工具只实现 `knowledge_search`）、`RetrievalService`（接口形状对，实现为 Stub） |
| 未落地 | **6** | `DocumentReadService`、`ExternalEvidenceService`、`EvidenceSufficiencyService`、`RagGuardMiddleware`、`CitationService`、`RetrievalTraceRecorder` |

这不是偏差——TASK-001 的目标就是先用 Stub 验证契约闭环，真实实现属于后续任务。把"2 完全 + 2 部分"读成"RAG 已完成一半"是错的：落地的部分都是**外壳与契约**，真正决定检索质量的组件（复合检索、充分性判断、grounding 校验）**一个都没落地**。

---

## 23. 第三步完成标准自检

| # | 标准 | 结果 | 落点 |
|---|---|:--:|---|
| 1 | 架构图只包含当前真实组件 | ✅ | §13；未实现组件全部隔离在 §21 |
| 2 | general / knowledge / 非法模式都有独立时序 | ✅ | §16.1 / §16.2 / §16.3 |
| 3 | DeerFlow 与 RAG Extension 职责边界清楚 | ✅ | §13（4 条硬约束）+ §15（14 项所有权表） |
| 4 | Evidence、Trace、安装链路均可追踪 | ✅ | §17（每节点标实现模块）、§18（三类数据分界）、§19（四段链路 + 行号） |
| 5 | 原生 MCP / Skill 标记为复用而非重新实现 | ✅ | §20（8 项全标「复用」，附原设计 §4 禁令） |
| 6 | 所有未来组件明确标记为「未实现」 | ✅ | §21（4 类共 20 项，均不接入主链） |
| 7 | 读者不会把当前 Stub 闭环误认为完整 Agentic RAG | ✅ | §21.4 定位声明 + §22 差距对照表 + knowledge 时序里显式标注「不是固定两步 Pipeline」 |
