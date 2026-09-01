"""End-to-end: explicit rag_mode drives the stub evidence loop through a real create_agent graph.

Locks the TASK-001 acceptance behavior through a real ``create_agent`` graph:
  knowledge mode -> knowledge_search schema bound -> tool executes -> structured
                   evidence envelope with run/tool-call provenance -> ledger rows
  general mode   -> knowledge_search schema hidden from the model -> a smuggled
                   call is blocked by the middleware -> native toolset preserved
  absent mode    -> identical to general (native default)
"""

import asyncio
import json

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as as_tool

from deerflow.agents.thread_state import ThreadState
from deerflow.extensions import reset_loaded_extensions, set_loaded_extensions
from deerflow.extensions.loader import ExtensionSpec, load_extensions

from deerflow_extension_api import EXTENSION_TASK_STORE_KEY, ExtensionData

from rag_extension.ledger import RagTaskLedger
from rag_extension.middleware import KNOWLEDGE_POLICY_MESSAGE_NAME, KnowledgeModeMiddleware
from rag_extension.tools import KNOWLEDGE_SEARCH_TOOL_NAME, knowledge_search


@pytest.fixture(autouse=True)
def _load_rag_extension_plugin():
    loaded, _ = load_extensions([ExtensionSpec(use="rag_extension:install", enabled=True)])
    set_loaded_extensions(loaded)
    yield
    reset_loaded_extensions()


@as_tool
def native_tool(x: str) -> str:
    "A native DeerFlow tool."
    return x


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
        self._seen_messages.append([(getattr(m, "type", None), getattr(m, "name", None)) for m in messages])
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _tool_call(query="rag extension stub"):
    return AIMessage(content="", tool_calls=[{"name": KNOWLEDGE_SEARCH_TOOL_NAME, "args": {"query": query}, "id": "c1", "type": "tool_call"}])


def _tool_messages(result):
    return [message for message in result["messages"] if isinstance(message, ToolMessage) and message.name == KNOWLEDGE_SEARCH_TOOL_NAME]


def test_knowledge_mode_full_evidence_loop() -> None:
    bound: list[list[str]] = []
    seen_messages: list[list[tuple]] = []
    model = RecordingModel(iter([_tool_call(), AIMessage(content="Based on evidence [E1], the stub returns fixed deterministic evidence.")]), bound, seen_messages)
    graph = create_agent(
        model=model,
        tools=[native_tool],
        middleware=[KnowledgeModeMiddleware()],
        state_schema=ThreadState,
    )
    task_store = ExtensionData("task-integration")
    context = {
        "rag_mode": "knowledge",
        "run_id": "run-integration-1",
        "thread_id": "thread-integration-1",
        EXTENSION_TASK_STORE_KEY: task_store,
    }

    result = asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="Search the knowledge base about the rag extension stub.")]}, context=context))

    assert KNOWLEDGE_SEARCH_TOOL_NAME in bound[0] and "native_tool" in bound[0]
    assert any(name == KNOWLEDGE_POLICY_MESSAGE_NAME for _, name in seen_messages[0])

    messages = _tool_messages(result)
    assert len(messages) == 1
    envelope = json.loads(messages[0].content)
    assert envelope["ok"] is True
    assert envelope["tool_call_id"] == "c1"
    assert envelope["trace_id"] == envelope["data"]["trace"]["retrieval_run_id"]
    evidence = envelope["data"]["evidence"]
    assert [item["evidence_id"] for item in evidence] == ["E1", "E2", "E3"]
    for item in evidence:
        assert item["provenance"]["run_id"] == "run-integration-1"
        assert item["provenance"]["thread_id"] == "thread-integration-1"
        assert item["provenance"]["tool_call_id"] == "c1"
        assert item["provenance"]["retrieval_run_id"] == envelope["trace_id"]
        assert len(item["content_hash"]) == 64
    assert envelope["data"]["errors"] == []
    assert envelope["data"]["degraded"] is False

    ledger = task_store.get(RagTaskLedger)
    assert ledger is not None
    snapshot = ledger.snapshot()
    assert snapshot["run_id"] == "run-integration-1"
    assert snapshot["searches"] == 1
    assert snapshot["evidence_count"] == 3
    assert snapshot["entries"][0]["tool_call_id"] == "c1"

    final = result["messages"][-1]
    assert isinstance(final, AIMessage) and "[E1]" in final.content


def test_general_mode_hides_schema_and_blocks_smuggled_call() -> None:
    bound: list[list[str]] = []
    seen_messages: list[list[tuple]] = []
    model = RecordingModel(iter([_tool_call(), AIMessage(content="Knowledge search is not available here.")]), bound, seen_messages)
    graph = create_agent(
        model=model,
        tools=[native_tool],
        middleware=[KnowledgeModeMiddleware()],
        state_schema=ThreadState,
    )

    result = asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content="Try to search the knowledge base anyway.")]},
            context={"rag_mode": "general", "run_id": "run-integration-2", "thread_id": "thread-integration-2"},
        )
    )

    assert KNOWLEDGE_SEARCH_TOOL_NAME not in bound[0]
    assert "native_tool" in bound[0]
    assert all(name != KNOWLEDGE_POLICY_MESSAGE_NAME for _, name in seen_messages[0])

    messages = _tool_messages(result)
    assert len(messages) == 1
    assert messages[0].status == "error"
    assert "not available" in messages[0].content
    assert messages[0].tool_call_id == "c1"


def test_absent_mode_defaults_to_native_toolset() -> None:
    bound: list[list[str]] = []
    seen_messages: list[list[tuple]] = []
    model = RecordingModel(iter([AIMessage(content="Answered without knowledge search.")]), bound, seen_messages)
    graph = create_agent(
        model=model,
        tools=[native_tool],
        middleware=[KnowledgeModeMiddleware()],
        state_schema=ThreadState,
    )

    result = asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="Just answer natively.")]}, context={"run_id": "run-integration-3"}))

    assert KNOWLEDGE_SEARCH_TOOL_NAME not in bound[0]
    assert "native_tool" in bound[0]
    assert all(name != KNOWLEDGE_POLICY_MESSAGE_NAME for _, name in seen_messages[0])
    assert _tool_messages(result) == []


def test_tool_defends_against_non_knowledge_mode_without_middleware() -> None:
    bound: list[list[str]] = []
    seen_messages: list[list[tuple]] = []
    model = RecordingModel(iter([_tool_call(), AIMessage(content="The tool refused to run.")]), bound, seen_messages)
    graph = create_agent(
        model=model,
        tools=[native_tool, knowledge_search],
        state_schema=ThreadState,
    )

    result = asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content="Call knowledge search in general mode.")]},
            context={"rag_mode": "general", "run_id": "run-integration-4"},
        )
    )

    assert KNOWLEDGE_SEARCH_TOOL_NAME in bound[0]
    messages = _tool_messages(result)
    assert len(messages) == 1
    envelope = json.loads(messages[0].content)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "rag_mode_not_knowledge"
    assert envelope["error"]["retryable"] is False
    assert envelope["data"] is None
