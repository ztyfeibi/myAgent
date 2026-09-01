"""Acceptance 7: RAG extension key behaviors are observable through DeerFlow's own Trace.

DeerFlow's backend-only audit trail is ``RunJournal`` -> ``RunEventStore``; the same
store backs ``GET /{thread_id}/runs/{run_id}/events`` (documented as debug/audit).
These tests drive the real ``RunManager`` + ``run_agent`` worker path with a
``MemoryRunEventStore`` installed, then read the run back through the store's own
``list_events`` API. Nothing in the trace layer is mocked and the extension gains no
new instrumentation: everything asserted here is what DeerFlow already records.

What the trace shows, and why it is enough for TASK-001:

- mode gating -> the recorded ``llm.ai.response`` carries (or does not carry) a
  ``knowledge_search`` tool call, because the middleware filters the bound schema;
- evidence -> the recorded ``llm.tool.result`` is the full Evidence envelope, so
  evidence ids and provenance (run_id / thread_id) are readable after the run;
- run outcome -> ``run.start`` / ``run.end`` (with ``status``) / ``run.error``.

**Not** observable here, and deliberately not asserted: the injected knowledge
policy ``SystemMessage``. It is built per model call and never written back to the
``messages`` channel, so it appears neither in the event store nor in checkpoint
state. It is observable only at runtime, in the message list handed to the model
(asserted in ``test_rag_extension_gateway.py``). Making it a first-class
``middleware:rag`` trace event would need harness support: ``RunJournal`` is not
exported through ``deerflow_extension_api`` (only reachable via the internal
``runtime.context["__run_journal"]`` key) and ``rag`` is not in
``MIDDLEWARE_EVENT_TAGS``.

HTTP/SSE remains out of scope (see TASK-001 §7.2); this file observes the same
run-level events the HTTP endpoint serves.
"""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool as as_tool
from langgraph.checkpoint.memory import InMemorySaver
from rag_extension.tools import KNOWLEDGE_SEARCH_TOOL_NAME

from deerflow.agents.middlewares.configured_extensions import load_configured_extension_middlewares
from deerflow.agents.thread_state import ThreadState
from deerflow.config.app_config import AppConfig
from deerflow.extensions import reset_loaded_extensions, set_loaded_extensions
from deerflow.extensions.loader import ExtensionSpec, load_extensions
from deerflow.runtime.events.store.memory import MemoryRunEventStore
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
    """Records the bound tool names so the trace can be cross-checked against binding."""

    def __init__(self, messages, bound):
        super().__init__(messages=messages)
        self._bound = bound

    def bind_tools(self, tools, **kwargs):
        self._bound.append([getattr(tool, "name", None) for tool in tools])
        return self


@dataclass
class TracedTurn:
    """One ``run_agent`` turn plus everything DeerFlow recorded about it."""

    record: Any
    bound: list[list[str]]
    events: list[dict[str, Any]]
    event_store: Any

    def of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["event_type"] == event_type]

    @property
    def event_types(self) -> list[str]:
        return [event["event_type"] for event in self.events]

    @property
    def serialized_events(self) -> str:
        return json.dumps(self.events, default=str)


def _knowledge_tool_call(query: str = "rag extension stub") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": KNOWLEDGE_SEARCH_TOOL_NAME, "args": {"query": query}, "id": "c1", "type": "tool_call"}])


def _tool_call_names(ai_event: dict[str, Any]) -> list[str]:
    content = ai_event["content"]
    tool_calls = content.get("tool_calls") if isinstance(content, dict) else None
    return [call.get("name") for call in tool_calls or []]


async def _run_traced_turn(
    *,
    mode: str | None,
    responses: list[AIMessage],
    loaded,
    app_config: AppConfig,
    thread_id: str = "thread-rag",
    event_store: MemoryRunEventStore | None = None,
) -> TracedTurn:
    bound: list[list[str]] = []
    event_store = event_store or MemoryRunEventStore()
    checkpointer = InMemorySaver()

    async def _publish(run_id, event, payload):
        return None

    bridge = SimpleNamespace(publish=_publish, publish_end=AsyncMock(), cleanup=AsyncMock())
    middlewares = load_configured_extension_middlewares(app_config)

    def agent_factory(*, config, app_config=None):
        return create_agent(
            model=RecordingModel(iter(responses), bound),
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
        ctx=RunContext(checkpointer=checkpointer, store=None, event_store=event_store, app_config=app_config, extensions=loaded),
        agent_factory=agent_factory,
        graph_input={"messages": [HumanMessage(content="Search the knowledge base about the rag extension stub.")]},
        # Mirrors build_run_config(): body.config.context is copied verbatim.
        config={"configurable": {"thread_id": thread_id}, "context": {} if mode is None else {"rag_mode": mode}},
    )

    # The same store backs the HTTP debug/audit endpoint; reading it directly here
    # keeps the assertion on the recorded data rather than on the transport.
    events = list(await event_store.list_events(thread_id, record.run_id))
    return TracedTurn(record, bound, events, event_store)


@pytest.mark.asyncio
async def test_knowledge_mode_evidence_is_observable_in_run_events() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    turn = await _run_traced_turn(
        mode="knowledge",
        responses=[_knowledge_tool_call(), AIMessage(content="Based on evidence [E1], the stub returns fixed deterministic evidence.")],
        loaded=loaded,
        app_config=app_config,
    )

    assert turn.record.status is RunStatus.success
    assert "run.start" in turn.event_types
    assert "run.end" in turn.event_types

    # Mode gating: the model was offered knowledge_search and asked for it.
    assert turn.bound[0] == [KNOWLEDGE_SEARCH_TOOL_NAME, "native_tool"]
    ai_events = turn.of_type("llm.ai.response")
    assert KNOWLEDGE_SEARCH_TOOL_NAME in _tool_call_names(ai_events[0])
    assert ai_events[-1]["content"]["content"].startswith("Based on evidence [E1]")

    # Evidence: the tool result recorded in the trace is the full envelope.
    tool_results = turn.of_type("llm.tool.result")
    assert len(tool_results) == 1
    envelope = json.loads(tool_results[0]["content"]["content"])
    assert envelope["ok"] is True
    assert [item["evidence_id"] for item in envelope["data"]["evidence"]] == ["E1", "E2", "E3"]
    assert {item["provenance"]["run_id"] for item in envelope["data"]["evidence"]} == {turn.record.run_id}
    assert {item["provenance"]["thread_id"] for item in envelope["data"]["evidence"]} == {"thread-rag"}

    assert turn.of_type("run.end")[0]["metadata"]["status"] == "success"


@pytest.mark.asyncio
async def test_general_mode_leaves_no_knowledge_evidence_in_run_events() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    turn = await _run_traced_turn(mode="general", responses=[AIMessage(content="answered natively")], loaded=loaded, app_config=app_config)

    assert turn.record.status is RunStatus.success
    assert turn.bound[0] == ["native_tool"]
    assert turn.of_type("llm.tool.result") == []
    assert KNOWLEDGE_SEARCH_TOOL_NAME not in turn.serialized_events
    assert "E1" not in turn.serialized_events
    assert turn.of_type("run.end")[0]["metadata"]["status"] == "success"


@pytest.mark.asyncio
async def test_invalid_mode_is_recorded_as_run_error_in_run_events() -> None:
    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])

    turn = await _run_traced_turn(mode="auto", responses=[AIMessage(content="should never be produced")], loaded=loaded, app_config=app_config)

    assert turn.record.status is RunStatus.error
    assert turn.of_type("run.error")
    # The model never ran, so no response/tool result could be recorded.
    assert turn.of_type("llm.ai.response") == []
    assert turn.of_type("llm.tool.result") == []


@pytest.mark.asyncio
async def test_extension_disabled_leaves_no_knowledge_evidence_in_run_events() -> None:
    app_config = _app_config(middlewares=[])

    turn = await _run_traced_turn(mode="knowledge", responses=[AIMessage(content="answered natively")], loaded=None, app_config=app_config)

    assert turn.record.status is RunStatus.success
    assert turn.bound[0] == ["native_tool"]
    assert turn.of_type("llm.tool.result") == []
    assert KNOWLEDGE_SEARCH_TOOL_NAME not in turn.serialized_events


@pytest.mark.asyncio
async def test_run_events_are_scoped_per_run_on_a_shared_thread() -> None:
    """Two knowledge turns on one thread keep their evidence attributable to their own run."""

    loaded = _load_rag_plugin()
    app_config = _app_config(middlewares=["rag_extension.middleware:KnowledgeModeMiddleware"])
    event_store = MemoryRunEventStore()

    responses = [_knowledge_tool_call(), AIMessage(content="Based on evidence [E1], the stub returns fixed deterministic evidence.")]
    first = await _run_traced_turn(mode="knowledge", responses=responses, loaded=loaded, app_config=app_config, event_store=event_store)
    second = await _run_traced_turn(mode="knowledge", responses=responses, loaded=loaded, app_config=app_config, event_store=event_store)

    assert first.record.run_id != second.record.run_id
    for turn in (first, second):
        tool_results = turn.of_type("llm.tool.result")
        assert len(tool_results) == 1
        envelope = json.loads(tool_results[0]["content"]["content"])
        # The envelope's own provenance must match the run that produced it, which is
        # what makes per-run attribution in the trace trustworthy.
        assert {item["provenance"]["run_id"] for item in envelope["data"]["evidence"]} == {turn.record.run_id}

    first_seqs = {event["seq"] for event in first.events}
    second_seqs = {event["seq"] for event in second.events}
    assert first_seqs and second_seqs
    assert first_seqs.isdisjoint(second_seqs)
