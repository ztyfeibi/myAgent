"""Gateway/RunManager-path tests: rag_mode travels config.context -> runtime.context.

These tests drive the real RunManager + worker path (``run_agent``) instead of
invoking ``create_agent(...).ainvoke()`` directly, so the chain under test is
the one a Gateway request takes:

    config["context"]["rag_mode"]
      -> worker ``_build_runtime_context`` -> ``runtime.context``
      -> KnowledgeModeMiddleware -> model binding
      -> knowledge_search -> ToolMessage -> bridge payloads

The model is the only fake: it is a scripted ``GenericFakeChatModel`` so the
tool loop, middleware hooks, extension task store and worker streaming are all
real. HTTP/SSE-over-HTTP is still out of scope here (see TASK-001 §7.2); what
these tests assert is the run-level payload the HTTP layer would publish.

The eight scenarios below mirror the TASK-001 step-8 checklist one-for-one, so
a failure names the scenario that regressed.
"""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from deerflow_extension_api import EXTENSION_TASK_STORE_KEY
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool as as_tool
from langgraph.checkpoint.memory import InMemorySaver
from rag_extension.ledger import RagTaskLedger
from rag_extension.middleware import KNOWLEDGE_POLICY_MESSAGE_NAME
from rag_extension.tools import KNOWLEDGE_SEARCH_TOOL_NAME

from deerflow.agents.middlewares.configured_extensions import load_configured_extension_middlewares
from deerflow.agents.thread_state import ThreadState
from deerflow.config.app_config import AppConfig
from deerflow.extensions import reset_loaded_extensions, set_loaded_extensions
from deerflow.extensions.loader import ExtensionSpec, load_extensions
from deerflow.runtime.runs.manager import RunManager
from deerflow.runtime.runs.schemas import RunStatus
from deerflow.runtime.runs.worker import RunContext, run_agent


@as_tool
def native_tool(x: str) -> str:
    "A native DeerFlow tool."
    return x


@pytest.fixture(autouse=True)
def _isolated_extension_state():
    reset_loaded_extensions()
    yield
    reset_loaded_extensions()


def _load_rag_plugin():
    loaded, diagnostics = load_extensions([ExtensionSpec(use="rag_extension:install", enabled=True)])
    assert diagnostics == []
    set_loaded_extensions(loaded)
    return loaded


def _app_config(*, middlewares: list[str]) -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "extensions": {"middlewares": middlewares},
        }
    )


class RecordingModel(GenericFakeChatModel):
    """Records the bound tool names and the message stream of every model call."""

    def __init__(self, messages, bound, seen_messages):
        super().__init__(messages=messages)
        self._bound = bound
        self._seen_messages = seen_messages

    def bind_tools(self, tools, **kwargs):
        self._bound.append([getattr(tool, "name", None) for tool in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen_messages.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class RuntimeContextSpy(AgentMiddleware[AgentState]):
    """Records the ``runtime.context`` the worker installed for each model call."""

    def __init__(self, seen: list[dict[str, Any]]) -> None:
        self._seen = seen

    async def awrap_model_call(self, request, handler):
        context = getattr(request.runtime, "context", None)
        entry: dict[str, Any] = {"context": dict(context) if isinstance(context, dict) else {}}
        task_store = entry["context"].get(EXTENSION_TASK_STORE_KEY)
        ledger = task_store.get(RagTaskLedger) if task_store is not None else None
        entry["ledger"] = ledger.snapshot() if ledger is not None else None
        self._seen.append(entry)
        return await handler(request)


@dataclass
class TurnResult:
    """Everything one ``run_agent`` turn produced, for assertions."""

    record: Any
    bound: list[list[str]]
    messages: list[list[Any]]
    contexts: list[dict[str, Any]]
    published: list[tuple[str, Any]]

    @property
    def published_json(self) -> str:
        return json.dumps([payload for _, payload in self.published], default=str)

    @property
    def final_values(self) -> dict[str, Any] | None:
        """Last ``values`` frame: the worker's final run state, i.e. the run result."""
        final = None
        for event, payload in self.published:
            if event == "values" and isinstance(payload, dict):
                final = payload
        return final

    @property
    def final_values_messages(self) -> list[Any]:
        return list((self.final_values or {}).get("messages") or [])

    @property
    def final_answer(self) -> str:
        for message in reversed(self.final_values_messages):
            if isinstance(message, dict):
                if message.get("type") == "ai":
                    return message.get("content") or ""
            elif isinstance(message, AIMessage):
                return message.content or ""
        return ""


def _knowledge_tool_call(query: str = "rag extension stub") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": KNOWLEDGE_SEARCH_TOOL_NAME, "args": {"query": query}, "id": "c1", "type": "tool_call"}])


def _model_tool_messages(messages: list[Any]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage) and message.name == KNOWLEDGE_SEARCH_TOOL_NAME]


def _policy_messages(messages: list[Any]) -> list[SystemMessage]:
    return [message for message in messages if isinstance(message, SystemMessage) and message.name == KNOWLEDGE_POLICY_MESSAGE_NAME]


def _frame_tool_messages(frame: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Evidence ToolMessages inside one published ``values`` frame (bridge payloads)."""
    if not isinstance(frame, dict):
        return []
    return [message for message in frame.get("messages") or [] if isinstance(message, dict) and message.get("name") == KNOWLEDGE_SEARCH_TOOL_NAME]


def _parse_envelope(message: Any) -> dict[str, Any]:
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
    return json.loads(content)


async def _run_turn(
    *,
    mode: str | None,
    responses: list[AIMessage],
    loaded,
    app_config: AppConfig,
    thread_id: str = "thread-rag",
) -> TurnResult:
    bound: list[list[str]] = []
    messages: list[list[Any]] = []
    contexts: list[dict[str, Any]] = []
    published: list[tuple[str, Any]] = []

    async def _publish(run_id, event, payload):
        published.append((event, payload))

    bridge = SimpleNamespace(publish=_publish, publish_end=AsyncMock(), cleanup=AsyncMock())
    middlewares = [*load_configured_extension_middlewares(app_config), RuntimeContextSpy(contexts)]

    def agent_factory(*, config, app_config=None):
        return create_agent(
            model=RecordingModel(iter(responses), bound, messages),
            tools=[native_tool],
            middleware=middlewares,
            state_schema=ThreadState,
        )

    manager = RunManager()
    record = await manager.create(thread_id, assistant_id="lead")
    await run_agent(
        bridge,
        manager,
        record,
        ctx=RunContext(checkpointer=InMemorySaver(), store=None, event_store=None, app_config=app_config, extensions=loaded),
        agent_factory=agent_factory,
        graph_input={"messages": [HumanMessage(content="Search the knowledge base about the rag extension stub.")]},
        # Mirrors build_run_config(): the checkpointer scopes state by
        # configurable.thread_id while body.config.context is copied verbatim.
        config={"configurable": {"thread_id": thread_id}, "context": {} if mode is None else {"rag_mode": mode}},
    )
    return TurnResult(record, bound, messages, contexts, published)


_KNOWLEDGE_RESPONSES = [_knowledge_tool_call(), AIMessage(content="Based on evidence [E1], the stub returns fixed deterministic evidence.")]


# Scenario 1 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_01_gateway_accepts_general_mode() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="general", responses=[AIMessage(content="answered natively")], loaded=loaded, app_config=app_config)

    assert result.record.status is RunStatus.success
    assert result.bound[0] == ["native_tool"]
    assert _policy_messages(result.messages[0]) == []
    assert _model_tool_messages(result.messages[0]) == []
    assert KNOWLEDGE_SEARCH_TOOL_NAME not in result.published_json
    assert result.final_answer == "answered natively"
    assert "E1" not in result.final_answer


# Scenario 2 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_02_gateway_accepts_knowledge_mode() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="knowledge", responses=_KNOWLEDGE_RESPONSES, loaded=loaded, app_config=app_config)

    assert result.record.status is RunStatus.success
    assert result.bound[0] == [KNOWLEDGE_SEARCH_TOOL_NAME, "native_tool"]
    assert len(_policy_messages(result.messages[0])) == 1


# Scenario 3 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_03_invalid_mode_is_rejected() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="auto", responses=[AIMessage(content="should never be produced")], loaded=loaded, app_config=app_config)

    assert result.record.status is RunStatus.error
    assert "invalid rag_mode" in (result.record.error or "")
    # Fails closed before the model is ever invoked.
    assert result.bound == []
    assert result.messages == []
    assert _frame_tool_messages(result.final_values) == []
    # The run stopped before the model ran, so the final state holds the human turn only.
    assert result.final_values is not None
    assert [message.get("type") for message in result.final_values_messages if isinstance(message, dict)] == ["human"]


# Scenario 4 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_04_extension_is_loaded_during_the_real_run() -> None:
    """The plugin's task-lifecycle contributor must run inside a real RunManager run."""

    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="knowledge", responses=_KNOWLEDGE_RESPONSES, loaded=loaded, app_config=app_config)

    assert result.record.status is RunStatus.success
    # on_task_start allocated the ledger and bound it to this run before the model saw it.
    first = result.contexts[0]
    assert EXTENSION_TASK_STORE_KEY in first["context"]
    assert first["ledger"] is not None
    assert first["ledger"]["run_id"] == result.record.run_id
    assert first["ledger"]["searches"] == 0

    # The stub search registered evidence through that ledger during the run.
    last = result.contexts[-1]
    assert last["ledger"]["run_id"] == result.record.run_id
    assert last["ledger"]["searches"] == 1
    assert last["ledger"]["evidence_count"] == 3
    entries = last["ledger"]["entries"]
    assert len(entries) == 3
    assert {entry["evidence"]["evidence_id"] for entry in entries} == {"E1", "E2", "E3"}
    assert {entry["tool_call_id"] for entry in entries} == {"c1"}
    assert {entry["retrieval_run_id"] for entry in entries} == {entries[0]["retrieval_run_id"]}
    assert all(entry["validation_status"] == "valid" for entry in entries)


# Scenario 5 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_05_runtime_context_carries_the_mode() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    knowledge = await _run_turn(mode="knowledge", responses=_KNOWLEDGE_RESPONSES, loaded=loaded, app_config=app_config)
    general = await _run_turn(mode="general", responses=[AIMessage(content="answered natively")], loaded=loaded, app_config=app_config)
    default = await _run_turn(mode=None, responses=[AIMessage(content="answered natively")], loaded=loaded, app_config=app_config)

    assert knowledge.contexts[0]["context"]["rag_mode"] == "knowledge"
    assert general.contexts[0]["context"]["rag_mode"] == "general"
    # Absent rag_mode must behave exactly like general (no auto mode exists).
    assert "rag_mode" not in default.contexts[0]["context"]
    assert default.bound[0] == ["native_tool"]
    assert _policy_messages(default.messages[0]) == []

    # The worker seeds correlation ids into the same context the extension reads.
    for turn in (knowledge, general):
        context = turn.contexts[0]["context"]
        assert context["run_id"] == turn.record.run_id
        assert context["thread_id"] == "thread-rag"


# Scenario 6 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_06_stub_tool_executes_and_produces_a_tool_message() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="knowledge", responses=_KNOWLEDGE_RESPONSES, loaded=loaded, app_config=app_config)

    # The tool ran for real: the second model call received exactly one ToolMessage.
    tool_messages = _model_tool_messages(result.messages[1])
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "c1"

    envelope = _parse_envelope(tool_messages[0])
    assert envelope["ok"] is True
    assert envelope["error"] is None
    assert envelope["tool_call_id"] == "c1"
    assert [item["evidence_id"] for item in envelope["data"]["evidence"]] == ["E1", "E2", "E3"]
    for item in envelope["data"]["evidence"]:
        assert item["source_type"] == "knowledge"
        assert len(item["content_hash"]) == 64
        assert item["provenance"]["run_id"] == result.record.run_id
        assert item["provenance"]["thread_id"] == "thread-rag"
        assert item["provenance"]["retriever"] == "stub"
    assert envelope["data"]["trace"]["evidence_count"] == 3
    assert envelope["data"]["degraded"] is False


# Scenario 7 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_07_final_run_result_carries_stub_evidence() -> None:
    """The run's own final state -- the payload behind SSE -- must carry the evidence."""

    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    result = await _run_turn(mode="knowledge", responses=_KNOWLEDGE_RESPONSES, loaded=loaded, app_config=app_config)

    assert result.record.status is RunStatus.success
    assert result.final_values is not None

    frame_messages = _frame_tool_messages(result.final_values)
    assert len(frame_messages) == 1
    envelope = _parse_envelope(frame_messages[0])
    assert [item["evidence_id"] for item in envelope["data"]["evidence"]] == ["E1", "E2", "E3"]
    assert {item["provenance"]["run_id"] for item in envelope["data"]["evidence"]} == {result.record.run_id}

    assert result.final_answer == "Based on evidence [E1], the stub returns fixed deterministic evidence."

    general = await _run_turn(mode="general", responses=[AIMessage(content="answered natively")], loaded=loaded, app_config=app_config)
    assert _frame_tool_messages(general.final_values) == []
    assert "E1" not in general.final_answer


# Scenario 8 ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_08_native_toolset_is_untouched_when_extension_disabled() -> None:
    """With the extension disabled (no plugin, no configured middleware) a
    knowledge-mode request degrades to plain native DeerFlow behavior."""
    app_config = _app_config(middlewares=[])

    result = await _run_turn(mode="knowledge", responses=[AIMessage(content="answered natively")], loaded=None, app_config=app_config)

    assert result.record.status is RunStatus.success
    assert result.bound[0] == ["native_tool"]
    assert _policy_messages(result.messages[0]) == []
    assert KNOWLEDGE_SEARCH_TOOL_NAME not in result.published_json
    assert result.contexts[0]["ledger"] is None
    assert EXTENSION_TASK_STORE_KEY not in result.contexts[0]["context"]
    assert result.final_answer == "answered natively"
