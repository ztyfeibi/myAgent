"""The stub knowledge_search tool: fixed evidence in, contract envelope out."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Annotated, Any

from deerflow_extension_api import task_store_from_runtime
from langchain.tools import InjectedToolCallId, ToolRuntime, tool

from rag_extension.contracts import (
    STUB_PROFILE_VERSION,
    Evidence,
    RetrievalRequest,
    RetrievalResponse,
    TemporalConstraint,
    ToolError,
    ToolResult,
)
from rag_extension.ledger import RagTaskLedger
from rag_extension.modes import KNOWLEDGE_MODE, resolve_rag_mode
from rag_extension.retrieval import StubRetrievalService

KNOWLEDGE_SEARCH_TOOL_NAME = "knowledge_search"

Runtime = ToolRuntime[dict[str, Any], Any]

_MODE_ERROR_CODE = "rag_mode_not_knowledge"
_STUB_TOP_K = 5


def _runtime_context(runtime: Any) -> dict[str, Any]:
    context = getattr(runtime, "context", None)
    return context if isinstance(context, dict) else {}


def _envelope_json(envelope: ToolResult) -> str:
    return json.dumps(envelope.to_dict(), ensure_ascii=False)


def _error_envelope(tool_call_id: str, mode: str) -> str:
    error = ToolError(
        code=_MODE_ERROR_CODE,
        message=(f"knowledge_search is available only in {KNOWLEDGE_MODE!r} mode; the current run is in {mode!r} mode."),
        retryable=False,
        component="rag_extension",
    )
    return _envelope_json(ToolResult(ok=False, data=None, error=error, trace_id="", tool_call_id=tool_call_id))


def _stamp_run_provenance(evidence: Sequence[Evidence], correlation: dict[str, Any], tool_call_id: str) -> list[Evidence]:
    stamps = {**correlation, "tool_call_id": tool_call_id}
    return [replace(item, provenance={**item.provenance, **stamps}) for item in evidence]


@tool(KNOWLEDGE_SEARCH_TOOL_NAME)
async def knowledge_search(
    runtime: Runtime,
    query: Annotated[str, "The search query to run against the knowledge base."],
    tool_call_id: Annotated[str, InjectedToolCallId],
    metadata_filter: Annotated[dict[str, Any] | None, "Optional metadata equality filters applied before retrieval."] = None,
    temporal_constraint: Annotated[dict[str, Any] | None, "Optional time-window constraint on document timestamps."] = None,
) -> str:
    """Search the knowledge base and return structured, traceable evidence.

    Returns a JSON envelope whose data.evidence list carries fixed stub evidence
    for TASK-001. Cite the evidence you relied on in the final answer using
    bracketed evidence ids (e.g. [E1]) and base factual statements only on the
    returned evidence.
    """
    context = _runtime_context(runtime)
    mode = resolve_rag_mode(context)
    if mode != KNOWLEDGE_MODE:
        return _error_envelope(tool_call_id, mode)

    request = RetrievalRequest(
        original_query=query,
        resolved_query=query,
        metadata_filter=metadata_filter,
        temporal_constraint=TemporalConstraint.from_dict(temporal_constraint) if temporal_constraint is not None else None,
        top_k=_STUB_TOP_K,
        profile_version=STUB_PROFILE_VERSION,
        trace_id=context.get("trace_id") or "",
    )
    response = await StubRetrievalService().retrieve(request)

    correlation = {key: context[key] for key in ("run_id", "thread_id") if context.get(key) is not None}
    evidence = _stamp_run_provenance(response.evidence, correlation, tool_call_id)
    stamped = RetrievalResponse(evidence=evidence, trace=response.trace, degraded=response.degraded, errors=response.errors)

    task_store = task_store_from_runtime(runtime)
    if task_store is not None:
        ledger = task_store.get_or_init(RagTaskLedger, lambda: RagTaskLedger(run_id=correlation.get("run_id")))
        ledger.register_evidence(
            stamped.evidence,
            tool_call_id=tool_call_id,
            retrieval_run_id=stamped.trace.retrieval_run_id,
            run_id=correlation.get("run_id"),
        )

    envelope = ToolResult(
        ok=True,
        data=stamped,
        error=None,
        trace_id=stamped.trace.retrieval_run_id,
        tool_call_id=tool_call_id,
        artifact_refs=[],
    )
    return _envelope_json(envelope)
