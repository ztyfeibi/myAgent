"""Package-level tests: install() registration and task-lifecycle ledger behavior."""

from __future__ import annotations

import asyncio
from typing import Any

from deerflow_extension_api import ExtensionData, TaskInfo, TaskOutcome

from rag_extension import install
from rag_extension.contracts import STUB_PROFILE_VERSION, Evidence, RetrievalRequest, RetrievalResponse
from rag_extension.ledger import RagExtensionStats, RagTaskLedger
from rag_extension.retrieval import StubRetrievalService


class FakeRegistry:
    def __init__(self) -> None:
        self.task_lifecycle_contributors: list[Any] = []

    def task_lifecycle(self, contributor: Any) -> None:
        self.task_lifecycle_contributors.append(contributor)


def _retrieve_request(query: str) -> RetrievalRequest:
    return RetrievalRequest(
        original_query=query,
        resolved_query=query,
        metadata_filter=None,
        temporal_constraint=None,
        top_k=5,
        profile_version=STUB_PROFILE_VERSION,
        trace_id="",
    )


async def _retrieve(query: str = "query") -> RetrievalResponse:
    return await StubRetrievalService().retrieve(_retrieve_request(query))


def test_install_registers_task_lifecycle() -> None:
    registry = FakeRegistry()

    install(registry, {})

    assert len(registry.task_lifecycle_contributors) == 1
    assert install.__deerflow_api__ == "0.2.0"
    assert install.__deerflow_name__ == "rag-extension"


def test_disabled_extension_registers_nothing() -> None:
    registry = FakeRegistry()

    install(registry, {"enabled": False})

    assert registry.task_lifecycle_contributors == []


def test_lifecycle_allocates_ledger_and_absorbs_stats() -> None:
    registry = FakeRegistry()
    install(registry, {})
    lifecycle = registry.task_lifecycle_contributors[0]
    app_store = ExtensionData("app")
    task_store = ExtensionData("task-1")
    task = TaskInfo(task_id="task-1", run_id="run-1", thread_id="thread-1", kind="lead")

    async def exercise() -> None:
        await lifecycle.on_task_start(app_store, task_store, task)
        ledger = task_store.get(RagTaskLedger)
        assert ledger is not None and ledger.run_id == "run-1"
        response = await _retrieve("stub query")
        ledger.register_evidence(
            response.evidence,
            tool_call_id="call-1",
            retrieval_run_id=response.trace.retrieval_run_id,
            run_id="run-1",
        )
        await lifecycle.on_task_stop(app_store, task_store, task, TaskOutcome.COMPLETED)

    asyncio.run(exercise())

    assert task_store.get(RagTaskLedger) is None
    stats = app_store.get(RagExtensionStats)
    assert stats is not None
    snapshot = stats.snapshot()
    assert snapshot["searches"] == 1
    assert snapshot["evidence_registered"] == 3
    assert snapshot["tasks"] == {"completed": 1}


def test_ledger_snapshot_keeps_run_and_tool_call_linkage() -> None:
    ledger = RagTaskLedger(run_id="run-9")
    response = asyncio.run(_retrieve("query"))

    ledger.register_evidence(response.evidence, tool_call_id="call-9", retrieval_run_id=response.trace.retrieval_run_id, run_id="run-9")

    snapshot = ledger.snapshot()
    assert snapshot["run_id"] == "run-9"
    assert snapshot["searches"] == 1
    assert len(snapshot["entries"]) == 3
    entry = snapshot["entries"][0]
    assert entry["run_id"] == "run-9"
    assert entry["tool_call_id"] == "call-9"
    assert entry["retrieval_run_id"] == response.trace.retrieval_run_id
    assert entry["validation_status"] == "valid"
    assert isinstance(entry["evidence"], dict) and entry["evidence"]["evidence_id"] == "E1"


def test_evidence_is_immutable_contract_value() -> None:
    response = asyncio.run(_retrieve("q"))

    first: Evidence = response.evidence[0]

    try:
        first.content = "mutated"
    except Exception:
        pass
    else:
        raise AssertionError("Evidence must be frozen")


def test_evidence_freeze_covers_nested_containers() -> None:
    """frozen=True alone only stops rebinding; the nested containers must be read-only too."""

    response = asyncio.run(_retrieve("q"))
    first = response.evidence[0]

    try:
        first.provenance["retriever"] = "tampered"
    except Exception:
        pass
    else:
        raise AssertionError("Evidence.provenance must not accept item assignment")

    try:
        response.evidence.append(first)
    except Exception:
        pass
    else:
        raise AssertionError("RetrievalResponse.evidence must not be appendable")

    assert first.provenance["retriever"] == "stub"
    assert len(response.evidence) == response.trace.evidence_count
