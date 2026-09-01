"""Deterministic stub retrieval service: fixed evidence, real contract shape."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from rag_extension.contracts import (
    Evidence,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalTraceSummary,
)

STUB_SOURCE_NAME = "rag-extension-stub"


@dataclass(frozen=True)
class _StubDocument:
    evidence_id: str
    document_id: str
    title: str
    source_uri: str
    content: str


_STUB_DOCUMENTS: tuple[_StubDocument, ...] = (
    _StubDocument(
        evidence_id="E1",
        document_id="stub-doc-001",
        title="RAG Extension Stub Contract",
        source_uri="stub://rag-extension/docs/stub-contract",
        content=("knowledge_search is a stub in TASK-001: it returns fixed, deterministic evidence to validate the Evidence contract end to end without any external knowledge base, BM25 index, or vector store."),
    ),
    _StubDocument(
        evidence_id="E2",
        document_id="stub-doc-002",
        title="Explicit RAG Modes",
        source_uri="stub://rag-extension/docs/explicit-modes",
        content=(
            "The RAG extension exposes exactly two explicit modes, general and knowledge. General mode preserves native DeerFlow behavior; knowledge mode enables knowledge_search and answer-time evidence citation. There is no auto mode."
        ),
    ),
    _StubDocument(
        evidence_id="E3",
        document_id="stub-doc-003",
        title="Evidence Traceability",
        source_uri="stub://rag-extension/docs/evidence-traceability",
        content=("Every evidence item carries a stable evidence id, a content hash, and provenance fields linking it to the current run, the producing tool call, and the retrieval run, so answers can cite it as [E1], [E2], or [E3]."),
    ),
)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class StubRetrievalService:
    """RetrievalService-shaped stub (interface-spec §20) with fixed output."""

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        retrieval_run_id = uuid4().hex
        retrieved_at = datetime.now(UTC)
        temporal = request.temporal_constraint.to_dict() if request.temporal_constraint is not None else None
        evidence = [
            Evidence(
                evidence_id=document.evidence_id,
                content=document.content,
                title=document.title,
                source_type="knowledge",
                source_name=STUB_SOURCE_NAME,
                source_uri=document.source_uri,
                document_id=document.document_id,
                external_id=document.document_id,
                document_version="v1",
                source_revision="stub-1",
                index_version="stub-index-0",
                content_hash=_content_hash(document.content),
                retrieved_at=retrieved_at,
                authority="MEDIUM",
                provenance={
                    "retriever": "stub",
                    "engine": STUB_SOURCE_NAME,
                    "retrieval_run_id": retrieval_run_id,
                    "query": request.original_query,
                    "resolved_query": request.resolved_query,
                    "metadata_filter": request.metadata_filter,
                    "temporal_constraint": temporal,
                },
                artifact_ref=None,
            )
            for document in _STUB_DOCUMENTS
        ]
        trace = RetrievalTraceSummary(
            retrieval_run_id=retrieval_run_id,
            variant_count=1,
            candidate_count=len(evidence),
            evidence_count=len(evidence),
            fastpass_hit=False,
            degraded=False,
            profile_version=request.profile_version,
        )
        return RetrievalResponse(evidence=evidence, trace=trace, degraded=False, errors=[])
