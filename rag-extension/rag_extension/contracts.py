"""RAG extension data contracts.

Mirrors ``docs/architecture/04-interface-specification.md`` (Evidence,
RetrievalResponse, Tool Result Envelope, Ledger Entry) so the stub loop already
speaks the stable V1 contract shape.

Immutability is deep for every container these types own. ``frozen=True`` alone
only stops attribute rebinding: ``evidence.provenance["x"] = ...`` and
``response.evidence.append(...)`` would still succeed on the nested objects, so
an ``Evidence`` already registered in the ledger could be edited in place by any
later holder of the same payload. Nested ``dict`` / ``list`` fields are therefore
**copied** and coerced to ``MappingProxyType`` / ``tuple`` at construction.

The freeze is one level deep on purpose: values *inside* ``provenance`` keep
their own type (a nested ``dict`` stays a plain, JSON-serializable ``dict``).
``to_dict()`` is the escape hatch and always returns plain mutable containers,
so serializing or adapting a payload never touches contract state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal

SourceType = Literal["knowledge", "document", "mcp"]
Authority = Literal["HIGH", "MEDIUM", "LOW"]
ValidationStatus = Literal["valid", "rejected"]

STUB_PROFILE_VERSION = "stub-v0"


def _frozen_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Copy ``value`` (detaching it from the caller) and return a read-only view."""
    return None if value is None else MappingProxyType(dict(value))


def _frozen_items(value: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(value)


def _plain(value: Any) -> Any:
    """Recursively rebuild ``value`` with plain mutable containers, for ``to_dict()``."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"invalid datetime value: {value!r}")


@dataclass(frozen=True)
class Evidence:
    """A controlled, source-traceable quoted fragment (never unbounded full text)."""

    evidence_id: str
    content: str
    title: str | None
    source_type: SourceType
    source_name: str
    source_uri: str | None
    document_id: str | None
    external_id: str | None
    document_version: str | None
    source_revision: str | None
    index_version: str | None
    content_hash: str
    retrieved_at: datetime
    publish_time: datetime | None = None
    update_time: datetime | None = None
    authority: Authority = "MEDIUM"
    provenance: Mapping[str, Any] = field(default_factory=dict)
    artifact_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))

    def __getstate__(self) -> dict[str, Any]:
        # mappingproxy is not picklable, and a shallow copy is not enough:
        # provenance may nest another frozen mapping (e.g. metadata_filter).
        return {**self.__dict__, "provenance": _plain(self.provenance)}

    def __setstate__(self, state: dict[str, Any]) -> None:
        object.__setattr__(self, "__dict__", {**state, "provenance": _frozen_mapping(state["provenance"])})

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "content": self.content,
            "title": self.title,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_uri": self.source_uri,
            "document_id": self.document_id,
            "external_id": self.external_id,
            "document_version": self.document_version,
            "source_revision": self.source_revision,
            "index_version": self.index_version,
            "content_hash": self.content_hash,
            "retrieved_at": _iso(self.retrieved_at),
            "publish_time": _iso(self.publish_time),
            "update_time": _iso(self.update_time),
            "authority": self.authority,
            "provenance": _plain(self.provenance),
            "artifact_ref": self.artifact_ref,
        }


@dataclass(frozen=True)
class TemporalConstraint:
    """Time-window constraint on document timestamps (V1: optional bounds)."""

    before: datetime | None = None
    after: datetime | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TemporalConstraint:
        return cls(before=_parse_datetime(value.get("before")), after=_parse_datetime(value.get("after")))

    def to_dict(self) -> dict[str, Any]:
        return {"before": _iso(self.before), "after": _iso(self.after)}


@dataclass(frozen=True)
class RetrievalRequest:
    """Formal retrieval input (interface-spec §4)."""

    original_query: str
    resolved_query: str
    metadata_filter: Mapping[str, Any] | None
    temporal_constraint: TemporalConstraint | None
    top_k: int
    profile_version: str
    trace_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata_filter", _frozen_mapping(self.metadata_filter))

    def __getstate__(self) -> dict[str, Any]:
        metadata_filter = self.metadata_filter
        return {**self.__dict__, "metadata_filter": None if metadata_filter is None else _plain(metadata_filter)}

    def __setstate__(self, state: dict[str, Any]) -> None:
        object.__setattr__(self, "__dict__", {**state, "metadata_filter": _frozen_mapping(state["metadata_filter"])})

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "resolved_query": self.resolved_query,
            "metadata_filter": _plain(self.metadata_filter) if self.metadata_filter is not None else None,
            "temporal_constraint": self.temporal_constraint.to_dict() if self.temporal_constraint is not None else None,
            "top_k": self.top_k,
            "profile_version": self.profile_version,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class RetrievalError:
    component: str
    code: str
    retryable: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "code": self.code,
            "retryable": self.retryable,
            "message": self.message,
        }


@dataclass(frozen=True)
class RetrievalTraceSummary:
    retrieval_run_id: str
    variant_count: int
    candidate_count: int
    evidence_count: int
    fastpass_hit: bool
    degraded: bool
    profile_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_run_id": self.retrieval_run_id,
            "variant_count": self.variant_count,
            "candidate_count": self.candidate_count,
            "evidence_count": self.evidence_count,
            "fastpass_hit": self.fastpass_hit,
            "degraded": self.degraded,
            "profile_version": self.profile_version,
        }


@dataclass(frozen=True)
class RetrievalResponse:
    evidence: tuple[Evidence, ...]
    trace: RetrievalTraceSummary
    degraded: bool
    errors: tuple[RetrievalError, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _frozen_items(self.evidence))
        object.__setattr__(self, "errors", _frozen_items(self.errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": [item.to_dict() for item in self.evidence],
            "trace": self.trace.to_dict(),
            "degraded": self.degraded,
            "errors": [item.to_dict() for item in self.errors],
        }


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    retryable: bool
    component: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "component": self.component,
        }


@dataclass(frozen=True)
class ToolResult:
    """Structured envelope; ``ok=false`` never carries plausible evidence data."""

    ok: bool
    data: RetrievalResponse | None
    error: ToolError | None
    trace_id: str
    tool_call_id: str
    artifact_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_refs", _frozen_items(self.artifact_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data.to_dict() if self.data is not None else None,
            "error": self.error.to_dict() if self.error is not None else None,
            "trace_id": self.trace_id,
            "tool_call_id": self.tool_call_id,
            "artifact_refs": list(self.artifact_refs),
        }


@dataclass(frozen=True)
class EvidenceLedgerEntry:
    """One run-scoped ledger row linking evidence to its producing tool call."""

    evidence: Evidence
    run_id: str
    tool_call_id: str
    retrieval_run_id: str | None
    validation_status: ValidationStatus
    registered_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.to_dict(),
            "run_id": self.run_id,
            "tool_call_id": self.tool_call_id,
            "retrieval_run_id": self.retrieval_run_id,
            "validation_status": self.validation_status,
            "registered_at": _iso(self.registered_at),
        }
