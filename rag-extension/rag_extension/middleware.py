"""Knowledge-mode middleware: explicit mode gating that preserves native behavior.

General mode (the default, also when ``rag_mode`` is absent) keeps the model-
visible toolset identical to native DeerFlow by filtering the ``knowledge_search``
schema out of the model binding, and blocks execution of a smuggled call.
Knowledge mode keeps the tool visible and injects a knowledge-policy
``SystemMessage`` instructing evidence-grounded, citation-carrying answers.

The policy message is an *instruction*, not a constraint: TASK-001 only verifies
that it reaches the model call. Enforcing that the final answer actually cites
retrieved evidence is RagGuard's responsibility (deferred).

Wiring note: this middleware must be declared through ``extensions.middlewares``
(operator-trusted, full middleware powers) rather than a plugin-contributed
middleware, because isolated plugin middlewares cannot substitute model requests
and therefore cannot hide tool schemas in general mode. It is not a standalone
toggle: it refuses to run unless the rag-extension plugin (``rag_extension:install``)
is loaded and enabled, so the plugin and this middleware are enabled/disabled as one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from deerflow.extensions import get_loaded_extensions
from deerflow_extension_api import ContentKind, provenance_kwargs
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from rag_extension.modes import KNOWLEDGE_MODE, resolve_rag_mode
from rag_extension.tools import KNOWLEDGE_SEARCH_TOOL_NAME, knowledge_search

KNOWLEDGE_POLICY_MESSAGE_NAME = "rag_knowledge_policy"

_ENTRY_POINT = "rag_extension:install"

_KNOWLEDGE_POLICY = (
    "Knowledge mode is active. Use the knowledge_search tool to retrieve evidence before "
    "answering knowledge questions, cite the evidence you relied on with bracketed evidence "
    "ids (e.g. [E1]), and base factual statements only on retrieved evidence. When retrieved "
    "evidence does not support an answer, say so explicitly instead of guessing."
)


def _request_context(request: Any) -> dict[str, Any] | None:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    return context if isinstance(context, dict) else None


def _insert_after_leading_system_messages(messages: list, injected: list) -> list:
    index = 0
    while index < len(messages) and isinstance(messages[index], SystemMessage):
        index += 1
    return [*messages[:index], *injected, *messages[index:]]


def _extension_plugin_loaded() -> bool:
    loaded = get_loaded_extensions()
    if not loaded.has_task_lifecycle:
        return False
    return any(source == _ENTRY_POINT for source, _ in loaded.task_lifecycle)


class ExtensionNotWiredError(RuntimeError):
    """Raised when the RAG middleware is configured but its plugin is not loaded/enabled."""


class KnowledgeModeMiddleware(AgentMiddleware[AgentState]):
    """Route one agent between native general behavior and knowledge mode."""

    tools = [knowledge_search]

    def __init__(self) -> None:
        if not _extension_plugin_loaded():
            raise ExtensionNotWiredError(
                "KnowledgeModeMiddleware is configured in extensions.middlewares but the "
                "rag-extension plugin is not loaded/enabled. Enable the plugin "
                "(plugins: rag_extension:install, required: true) and restart, or remove this "
                "middleware entry; the plugin and this middleware are one toggle."
            )

    def _prepare_model_request(self, request: ModelRequest) -> ModelRequest:
        if resolve_rag_mode(_request_context(request)) == KNOWLEDGE_MODE:
            policy = SystemMessage(
                content=_KNOWLEDGE_POLICY,
                name=KNOWLEDGE_POLICY_MESSAGE_NAME,
                additional_kwargs=provenance_kwargs(ContentKind.MIDDLEWARE_INJECTION, KNOWLEDGE_POLICY_MESSAGE_NAME),
            )
            messages = _insert_after_leading_system_messages(list(request.messages), [policy])
            return request.override(messages=messages)
        active = [item for item in request.tools if getattr(item, "name", None) != KNOWLEDGE_SEARCH_TOOL_NAME]
        if len(active) == len(request.tools):
            return request
        return request.override(tools=active)

    def _blocked_tool_message(self, request: ToolCallRequest) -> ToolMessage | None:
        name = str(request.tool_call.get("name") or "")
        mode = resolve_rag_mode(_request_context(request))
        if name != KNOWLEDGE_SEARCH_TOOL_NAME or mode == KNOWLEDGE_MODE:
            return None
        return ToolMessage(
            content=(f"Error: knowledge_search is not available in {mode!r} mode; it is enabled only for explicit knowledge-mode runs."),
            tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
            name=name,
            status="error",
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._prepare_model_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(self._prepare_model_request(request))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Any],
    ) -> ToolMessage | Any:
        blocked = self._blocked_tool_message(request)
        if blocked is not None:
            return blocked
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Any]],
    ) -> ToolMessage | Any:
        blocked = self._blocked_tool_message(request)
        if blocked is not None:
            return blocked
        return await handler(request)
