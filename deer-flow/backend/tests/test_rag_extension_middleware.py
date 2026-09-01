"""Unit tests for KnowledgeModeMiddleware mode gating (schema filtering + call blocking)."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool as as_tool

from deerflow.extensions import reset_loaded_extensions, set_loaded_extensions
from deerflow.extensions.loader import ExtensionSpec, load_extensions

from rag_extension.middleware import (
    KNOWLEDGE_POLICY_MESSAGE_NAME,
    ExtensionNotWiredError,
    KnowledgeModeMiddleware,
)
from rag_extension.modes import RagModeError
from rag_extension.tools import KNOWLEDGE_SEARCH_TOOL_NAME


@as_tool
def native_tool(x: str) -> str:
    "A native DeerFlow tool."
    return x


class ModelRequestStub:
    def __init__(self, tools, *, messages=None, context=None):
        self.tools = tools
        self.messages = messages if messages is not None else []
        self.runtime = SimpleNamespace(context={} if context is None else context)

    def override(self, **updates):
        return ModelRequestStub(
            updates.get("tools", self.tools),
            messages=updates.get("messages", self.messages),
            context=self.runtime.context,
        )


class ToolRequestStub:
    def __init__(self, name, *, context=None):
        self.tool_call = {"name": name, "id": "call-1", "args": {}}
        self.runtime = SimpleNamespace(context={} if context is None else context)


def _names(request):
    return [getattr(tool, "name", None) for tool in request.tools]


@pytest.fixture(autouse=True)
def _load_rag_extension_plugin():
    loaded, _ = load_extensions([ExtensionSpec(use="rag_extension:install", enabled=True)])
    set_loaded_extensions(loaded)
    yield
    reset_loaded_extensions()


def test_middleware_contributes_knowledge_search_tool() -> None:
    assert [tool.name for tool in KnowledgeModeMiddleware.tools] == [KNOWLEDGE_SEARCH_TOOL_NAME]


def test_general_mode_filters_knowledge_search_schema_only() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub(list(KnowledgeModeMiddleware.tools) + [native_tool], context={"rag_mode": "general"})

    prepared = middleware._prepare_model_request(request)

    assert _names(prepared) == ["native_tool"]
    assert prepared.messages == []


def test_absent_mode_defaults_to_native_toolset() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub(list(KnowledgeModeMiddleware.tools) + [native_tool], context={})

    prepared = middleware._prepare_model_request(request)

    assert _names(prepared) == ["native_tool"]


def test_invalid_mode_fails_closed() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub(list(KnowledgeModeMiddleware.tools) + [native_tool], context={"rag_mode": "auto"})

    with pytest.raises(RagModeError, match="rag_mode"):
        middleware._prepare_model_request(request)


def test_knowledge_mode_keeps_tools_and_injects_policy_message() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub(list(KnowledgeModeMiddleware.tools) + [native_tool], context={"rag_mode": "knowledge"})

    prepared = middleware._prepare_model_request(request)

    assert _names(prepared) == [KNOWLEDGE_SEARCH_TOOL_NAME, "native_tool"]
    injected = [message for message in prepared.messages if isinstance(message, SystemMessage) and message.name == KNOWLEDGE_POLICY_MESSAGE_NAME]
    assert len(injected) == 1
    assert injected[0].additional_kwargs.get("deerflow_content_kind") == "middleware_injection"
    assert injected[0].additional_kwargs.get("deerflow_producer_kind") == KNOWLEDGE_POLICY_MESSAGE_NAME
    assert "[E1]" in injected[0].content


def test_general_mode_with_only_knowledge_tool_filters_to_empty() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub(list(KnowledgeModeMiddleware.tools), context={"rag_mode": "general"})

    prepared = middleware._prepare_model_request(request)

    assert _names(prepared) == []


def test_wrap_model_call_passes_prepared_request_to_handler() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub([native_tool], context={"rag_mode": "knowledge"})
    seen = {}

    def handler(prepared):
        seen["messages"] = prepared.messages
        return "model-response"

    assert middleware.wrap_model_call(request, handler) == "model-response"
    assert any(getattr(message, "name", None) == KNOWLEDGE_POLICY_MESSAGE_NAME for message in seen["messages"])


def test_wrap_tool_call_blocks_knowledge_search_in_general_mode() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ToolRequestStub(KNOWLEDGE_SEARCH_TOOL_NAME, context={"rag_mode": "general"})
    called = []

    def handler(_request):
        called.append(True)
        return "should-not-run"

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert result.name == KNOWLEDGE_SEARCH_TOOL_NAME
    assert "knowledge" in result.content
    assert called == []


def test_wrap_tool_call_allows_knowledge_search_in_knowledge_mode() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ToolRequestStub(KNOWLEDGE_SEARCH_TOOL_NAME, context={"rag_mode": "knowledge"})

    result = middleware.wrap_tool_call(request, lambda _request: "tool-ok")

    assert result == "tool-ok"


def test_wrap_tool_call_leaves_native_tools_untouched_in_general_mode() -> None:
    middleware = KnowledgeModeMiddleware()
    request = ToolRequestStub("native_tool", context={"rag_mode": "general"})

    result = middleware.wrap_tool_call(request, lambda _request: "native-ok")

    assert result == "native-ok"


def test_awrap_tool_call_blocks_knowledge_search_in_general_mode() -> None:
    import asyncio

    middleware = KnowledgeModeMiddleware()
    request = ToolRequestStub(KNOWLEDGE_SEARCH_TOOL_NAME, context={"rag_mode": "general"})

    async def handler(_request):
        return "should-not-run"

    result = asyncio.run(middleware.awrap_tool_call(request, handler))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"


def test_awrap_model_call_passes_prepared_request_to_handler() -> None:
    import asyncio

    middleware = KnowledgeModeMiddleware()
    request = ModelRequestStub([native_tool], context={"rag_mode": "general"})
    seen = {}

    async def handler(prepared):
        seen["tools"] = _names(prepared)
        return "model-response"

    assert asyncio.run(middleware.awrap_model_call(request, handler)) == "model-response"
    assert seen["tools"] == ["native_tool"]


def test_middleware_fails_closed_when_plugin_not_loaded() -> None:
    reset_loaded_extensions()

    with pytest.raises(ExtensionNotWiredError, match="plugin"):
        KnowledgeModeMiddleware()
