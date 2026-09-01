"""Explicit RAG mode contract, parsed and validated by the RAG middleware and tool.

The Gateway is intentionally RAG-agnostic: ``rag_mode`` reaches the extension
through the free-form ``body.config.context`` pass-through and is read back from
``runtime.context``. This module is the single place that parses and validates
the value (fail closed on invalid input).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

RAG_MODE_CONTEXT_KEY = "rag_mode"
GENERAL_MODE = "general"
KNOWLEDGE_MODE = "knowledge"
RAG_MODES: tuple[str, ...] = (GENERAL_MODE, KNOWLEDGE_MODE)
RagMode = Literal["general", "knowledge"]


class RagModeError(ValueError):
    """Structured, fail-closed error for an out-of-contract ``rag_mode`` value."""

    def __init__(self, value: Any) -> None:
        self.value = value
        self.code = "invalid_rag_mode"
        self.expected = RAG_MODES
        expected = " or ".join(repr(mode) for mode in RAG_MODES)
        super().__init__(f"invalid {RAG_MODE_CONTEXT_KEY}: {value!r}; expected {expected}")


def normalize_rag_mode(value: Any) -> str:
    """Normalize an explicit rag_mode value; ``None`` means the default general mode."""
    if value is None:
        return GENERAL_MODE
    if isinstance(value, str) and value in RAG_MODES:
        return value
    raise RagModeError(value)


def resolve_rag_mode(context: Mapping[str, Any] | None) -> str:
    """Resolve and validate the active RAG mode from a runtime context mapping.

    Absent/``None`` resolves to the default general (native) mode. A present but
    invalid value raises :class:`RagModeError` (fail closed) instead of silently
    degrading to general, so a typo cannot turn a strict knowledge-mode request
    into an ungrounded native answer.
    """
    if not context:
        return GENERAL_MODE
    value = context.get(RAG_MODE_CONTEXT_KEY)
    if value is None:
        return GENERAL_MODE
    return normalize_rag_mode(value)
