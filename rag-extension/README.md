# rag-extension (TASK-001)

DeerFlow RAG extension foundation: explicit `general` / `knowledge` modes and a
stub `knowledge_search` tool that closes the minimal evidence loop

```
Request -> rag_mode=knowledge -> knowledge_search -> structured Evidence -> cited answer
```

## What it contributes

| Piece | Mechanism | Where |
|---|---|---|
| `RagTaskLifecycle` (run-scoped evidence ledger allocation + stats absorption) | `plugins:` entry point (`install()`) | `rag_extension/lifecycle.py` |
| `KnowledgeModeMiddleware` (mode gating, tool schema filtering, policy message) | `extensions.middlewares` config entry | `rag_extension/middleware.py` |
| `knowledge_search` stub tool (contract-shaped evidence envelope) | middleware `tools` attribute | `rag_extension/tools.py` |
| Contracts (`Evidence`, `RetrievalResponse`, `ToolResult`, ledger entry) | dataclasses per interface spec | `rag_extension/contracts.py` |

## Why the middleware is not plugin-contributed

Plugin-contributed middlewares are wrapped in `IsolatedMiddleware`: their wrap
hooks are observational only and cannot substitute model requests. Hiding the
`knowledge_search` schema from the model in general mode requires
`request.override(tools=...)`, so the middleware must be wired through the
operator-trusted `extensions.middlewares` list (same pattern as
`DeferredToolFilterMiddleware`).

## Install (from the deer-flow repo root)

```bash
make extension-install SOURCE=../rag-extension
```

Then add to `config.yaml` (operator-trusted, additive):

```yaml
extensions:
  middlewares:
    - rag_extension.middleware:KnowledgeModeMiddleware
```

Restart the Gateway after both changes.

## Usage

Select the mode explicitly per run; there is no auto mode:

```jsonc
POST /api/threads/{thread_id}/runs
{
  "input": {"messages": [{"role": "user", "content": "..."}]},
  "context": {"rag_mode": "knowledge"}   // or "general"; omit for general (native)
}
```

Invalid values are rejected with HTTP 422 at the run boundary.

## Tests

```bash
# Backend suite (extension installed in backend venv)
cd ../deer-flow/backend && make test

# Package tests
uv run pytest tests
```
