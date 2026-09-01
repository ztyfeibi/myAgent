"""Contract tests for the rag-extension stub evidence loop (interface-spec conformance)."""

import asyncio
import copy
import json
import pickle
from datetime import datetime, timezone

import pytest

from rag_extension.contracts import (
    STUB_PROFILE_VERSION,
    Evidence,
    EvidenceLedgerEntry,
    RetrievalError,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalTraceSummary,
    TemporalConstraint,
    ToolError,
    ToolResult,
)
from rag_extension.retrieval import STUB_SOURCE_NAME, StubRetrievalService

_EVIDENCE_FIELDS = {
    "evidence_id",
    "content",
    "title",
    "source_type",
    "source_name",
    "source_uri",
    "document_id",
    "external_id",
    "document_version",
    "source_revision",
    "index_version",
    "content_hash",
    "retrieved_at",
    "publish_time",
    "update_time",
    "authority",
    "provenance",
    "artifact_ref",
}


def _retrieve():
    request = RetrievalRequest(
        original_query="what does the stub return?",
        resolved_query="what does the stub return?",
        metadata_filter=None,
        temporal_constraint=None,
        top_k=5,
        profile_version=STUB_PROFILE_VERSION,
        trace_id="test-trace-1",
    )
    return asyncio.run(StubRetrievalService().retrieve(request))


def test_stub_evidence_covers_full_contract_fieldset() -> None:
    response = _retrieve()

    assert response.evidence, "stub must return at least one evidence item"
    for item in response.evidence:
        payload = item.to_dict()
        assert set(payload) == _EVIDENCE_FIELDS
        assert item.source_type == "knowledge"
        assert item.source_name == STUB_SOURCE_NAME
        assert item.authority in ("HIGH", "MEDIUM", "LOW")
        assert item.retrieved_at.tzinfo == timezone.utc
        assert len(item.content_hash) == 64


def test_stub_response_serializes_json_safe_and_zero_failure_separated() -> None:
    response = _retrieve()

    payload = json.loads(json.dumps(response.to_dict()))
    assert payload["degraded"] is False
    assert payload["errors"] == []
    assert payload["trace"]["profile_version"] == STUB_PROFILE_VERSION
    assert payload["trace"]["evidence_count"] == len(payload["evidence"])
    assert payload["trace"]["candidate_count"] >= payload["trace"]["evidence_count"]
    assert payload["trace"]["retrieval_run_id"]
    for item in payload["evidence"]:
        assert item["provenance"]["retrieval_run_id"] == payload["trace"]["retrieval_run_id"]
        assert item["provenance"]["retriever"] == "stub"


def test_stub_is_deterministic_except_retrieval_timestamps() -> None:
    first = _retrieve()
    second = _retrieve()

    assert [item.evidence_id for item in first.evidence] == [item.evidence_id for item in second.evidence]
    assert [item.content for item in first.evidence] == [item.content for item in second.evidence]
    assert [item.content_hash for item in first.evidence] == [item.content_hash for item in second.evidence]
    assert first.trace.retrieval_run_id != second.trace.retrieval_run_id


def test_tool_result_envelope_consistency() -> None:
    response = _retrieve()
    ok_envelope = ToolResult(
        ok=True,
        data=response,
        error=None,
        trace_id=response.trace.retrieval_run_id,
        tool_call_id="call-1",
    )
    payload = json.loads(json.dumps(ok_envelope.to_dict()))
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["evidence"]
    assert payload["tool_call_id"] == "call-1"
    assert payload["trace_id"] == response.trace.retrieval_run_id

    error_envelope = ToolResult(
        ok=False,
        data=None,
        error=ToolError(code="rag_mode_not_knowledge", message="not enabled", retryable=False, component="rag_extension"),
        trace_id="",
        tool_call_id="call-2",
    )
    payload = json.loads(json.dumps(error_envelope.to_dict()))
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["retryable"] is False


def test_retrieval_error_shape_round_trips() -> None:
    error = RetrievalError(component="retriever", code="unavailable", retryable=True, message="backend down")

    payload = json.loads(json.dumps(error.to_dict()))
    assert payload == {"component": "retriever", "code": "unavailable", "retryable": True, "message": "backend down"}


def test_ledger_entry_links_evidence_to_run_and_tool_call() -> None:
    from datetime import datetime, timezone

    response = _retrieve()
    entry = EvidenceLedgerEntry(
        evidence=response.evidence[0],
        run_id="run-1",
        tool_call_id="call-1",
        retrieval_run_id=response.trace.retrieval_run_id,
        validation_status="valid",
        registered_at=datetime.now(timezone.utc),
    )
    payload = json.loads(json.dumps(entry.to_dict()))

    assert payload["run_id"] == "run-1"
    assert payload["tool_call_id"] == "call-1"
    assert payload["retrieval_run_id"] == response.trace.retrieval_run_id
    assert payload["validation_status"] == "valid"
    assert payload["evidence"]["evidence_id"] == response.evidence[0].evidence_id


def test_trace_summary_shape() -> None:
    trace = RetrievalTraceSummary(
        retrieval_run_id="rr-1",
        variant_count=1,
        candidate_count=3,
        evidence_count=3,
        fastpass_hit=False,
        degraded=False,
        profile_version=STUB_PROFILE_VERSION,
    )

    assert json.loads(json.dumps(trace.to_dict())) == {
        "retrieval_run_id": "rr-1",
        "variant_count": 1,
        "candidate_count": 3,
        "evidence_count": 3,
        "fastpass_hit": False,
        "degraded": False,
        "profile_version": STUB_PROFILE_VERSION,
    }


def test_evidence_contract_is_frozen() -> None:
    response = _retrieve()
    item: Evidence = response.evidence[0]

    try:
        item.content = "mutated"
    except Exception:
        return
    raise AssertionError("Evidence must be immutable")


def test_evidence_provenance_is_not_item_mutable() -> None:
    item = _retrieve().evidence[0]

    with pytest.raises(TypeError):
        item.provenance["injected"] = "tampered"

    assert "injected" not in item.provenance


def test_evidence_provenance_nested_filter_is_not_item_mutable() -> None:
    request = RetrievalRequest(
        original_query="q",
        resolved_query="q",
        metadata_filter={"scope": "kb"},
        temporal_constraint=None,
        top_k=5,
        profile_version=STUB_PROFILE_VERSION,
        trace_id="t-1",
    )
    item = Evidence(
        evidence_id="E1",
        content="c",
        title=None,
        source_type="knowledge",
        source_name="kb",
        source_uri=None,
        document_id="d",
        external_id=None,
        document_version=None,
        source_revision=None,
        index_version="i",
        content_hash="h" * 64,
        retrieved_at=datetime.now(timezone.utc),
        provenance={"metadata_filter": request.metadata_filter},
    )

    with pytest.raises(TypeError):
        item.provenance["metadata_filter"]["scope"] = "other"

    assert item.provenance["metadata_filter"]["scope"] == "kb"


def test_response_evidence_and_errors_are_not_appendable() -> None:
    response = _retrieve()

    with pytest.raises(AttributeError):
        response.evidence.append(response.evidence[0])
    with pytest.raises(AttributeError):
        response.errors.append(RetrievalError(component="c", code="c", retryable=False, message="m"))

    assert len(response.evidence) == response.trace.evidence_count
    assert response.errors == ()


def test_tool_result_artifact_refs_are_not_appendable() -> None:
    envelope = ToolResult(
        ok=True,
        data=_retrieve(),
        error=None,
        trace_id="t-1",
        tool_call_id="call-1",
        artifact_refs=["artifact://one"],
    )

    with pytest.raises(AttributeError):
        envelope.artifact_refs.append("artifact://two")

    assert envelope.artifact_refs == ("artifact://one",)


def test_retrieval_request_metadata_filter_is_read_only() -> None:
    request = RetrievalRequest(
        original_query="q",
        resolved_query="q",
        metadata_filter={"scope": "kb"},
        temporal_constraint=None,
        top_k=5,
        profile_version=STUB_PROFILE_VERSION,
        trace_id="t-1",
    )

    with pytest.raises(TypeError):
        request.metadata_filter["scope"] = "other"

    assert request.metadata_filter["scope"] == "kb"


def test_contracts_detach_from_caller_supplied_containers() -> None:
    provenance = {"stage": "original"}
    evidence = [
        Evidence(
            evidence_id="E1",
            content="c",
            title=None,
            source_type="knowledge",
            source_name="kb",
            source_uri=None,
            document_id="d",
            external_id=None,
            document_version=None,
            source_revision=None,
            index_version="i",
            content_hash="h" * 64,
            retrieved_at=datetime.now(timezone.utc),
            provenance=provenance,
        )
    ]
    artifact_refs = ["artifact://one"]

    response = RetrievalResponse(
        evidence=evidence,
        trace=RetrievalTraceSummary(
            retrieval_run_id="rr-1",
            variant_count=1,
            candidate_count=1,
            evidence_count=1,
            fastpass_hit=False,
            degraded=False,
            profile_version=STUB_PROFILE_VERSION,
        ),
        degraded=False,
    )
    envelope = ToolResult(ok=True, data=response, error=None, trace_id="t-1", tool_call_id="call-1", artifact_refs=artifact_refs)

    provenance["stage"] = "tampered"
    evidence.append(evidence[0])
    artifact_refs.append("artifact://two")

    assert response.evidence[0].provenance["stage"] == "original"
    assert len(response.evidence) == 1
    assert envelope.artifact_refs == ("artifact://one",)


def test_to_dict_returns_mutable_copies() -> None:
    response = _retrieve()
    payload = response.to_dict()

    payload["evidence"].append({"evidence_id": "bogus"})
    payload["evidence"][0]["content"] = "tampered"
    payload["evidence"][0]["provenance"]["retriever"] = "tampered"

    assert len(response.evidence) == response.trace.evidence_count
    assert response.evidence[0].content != "tampered"
    assert response.evidence[0].provenance["retriever"] == "stub"


def test_frozen_contracts_survive_deepcopy_and_pickle() -> None:
    response = _retrieve()

    for clone in (copy.deepcopy(response), pickle.loads(pickle.dumps(response))):
        assert [item.evidence_id for item in clone.evidence] == [item.evidence_id for item in response.evidence]
        assert clone.evidence[0].provenance["retriever"] == "stub"
        with pytest.raises(TypeError):
            clone.evidence[0].provenance["injected"] = "tampered"
        with pytest.raises(AttributeError):
            clone.evidence.append(clone.evidence[0])


def test_retrieval_request_contract_shape() -> None:
    request = RetrievalRequest(
        original_query="q",
        resolved_query="q",
        metadata_filter={"scope": "kb"},
        temporal_constraint=None,
        top_k=5,
        profile_version=STUB_PROFILE_VERSION,
        trace_id="t-1",
    )

    assert json.loads(json.dumps(request.to_dict())) == {
        "original_query": "q",
        "resolved_query": "q",
        "metadata_filter": {"scope": "kb"},
        "temporal_constraint": None,
        "top_k": 5,
        "profile_version": STUB_PROFILE_VERSION,
        "trace_id": "t-1",
    }


def test_temporal_constraint_round_trips() -> None:
    constraint = TemporalConstraint.from_dict({"before": "2026-01-01T00:00:00+00:00", "after": "2025-01-01T00:00:00Z"})

    assert json.loads(json.dumps(constraint.to_dict())) == {
        "before": "2026-01-01T00:00:00+00:00",
        "after": "2025-01-01T00:00:00+00:00",
    }
