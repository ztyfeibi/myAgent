"""Unit tests for the explicit rag_mode contract (resolution, defaults, fail-closed).

REBUILT 2026-08-30 -- NOT a verbatim recovery. The original file was one of six
untracked RAG tests destroyed by the sandboxed mass-deletion accident, and no
copy of its contents survived anywhere that could be searched (IDE history,
pytest caches, bytecode, git objects, terminal scrollback, WorkBuddy
changes-index and session logs). Only its size (45 lines) and case count
(14, from the recorded ``62 passed ... modes 14`` run) are known.

This file is therefore written to the same responsibility -- the explicit
``rag_mode`` contract -- against the current ``rag_extension.modes``
implementation, restoring the 14 lost cases. Wording of the original
assertions is not recoverable; see
``docs/task/TASK-001-rag-extension-foundation.md`` §7.12 for the recovery
ledger covering all six files.

The contract under test is the fail-closed rule that makes a typo safe: an
absent or ``None`` ``rag_mode`` means the native general mode, but a present
and invalid value raises instead of silently degrading, so a strict
knowledge-mode request can never turn into an ungrounded native answer.
"""

import pytest

from rag_extension.modes import (
    GENERAL_MODE,
    KNOWLEDGE_MODE,
    RAG_MODE_CONTEXT_KEY,
    RAG_MODES,
    RagModeError,
    normalize_rag_mode,
    resolve_rag_mode,
)


def test_absent_context_resolves_to_general() -> None:
    assert resolve_rag_mode(None) == GENERAL_MODE


def test_empty_context_resolves_to_general() -> None:
    assert resolve_rag_mode({}) == GENERAL_MODE


def test_context_without_mode_key_resolves_to_general() -> None:
    assert resolve_rag_mode({"unrelated": "value"}) == GENERAL_MODE


def test_none_mode_value_resolves_to_general() -> None:
    assert resolve_rag_mode({RAG_MODE_CONTEXT_KEY: None}) == GENERAL_MODE


def test_explicit_general_resolves_to_general() -> None:
    assert resolve_rag_mode({RAG_MODE_CONTEXT_KEY: GENERAL_MODE}) == GENERAL_MODE


def test_explicit_knowledge_resolves_to_knowledge() -> None:
    assert resolve_rag_mode({RAG_MODE_CONTEXT_KEY: KNOWLEDGE_MODE}) == KNOWLEDGE_MODE


def test_unknown_mode_fails_closed() -> None:
    with pytest.raises(RagModeError):
        resolve_rag_mode({RAG_MODE_CONTEXT_KEY: "auto"})


def test_empty_string_mode_fails_closed() -> None:
    with pytest.raises(RagModeError):
        resolve_rag_mode({RAG_MODE_CONTEXT_KEY: ""})


def test_mode_matching_is_case_sensitive() -> None:
    with pytest.raises(RagModeError):
        resolve_rag_mode({RAG_MODE_CONTEXT_KEY: "Knowledge"})


def test_mode_is_not_whitespace_tolerant() -> None:
    with pytest.raises(RagModeError):
        resolve_rag_mode({RAG_MODE_CONTEXT_KEY: "knowledge "})


def test_non_string_modes_fail_closed() -> None:
    for value in (True, 1, ["knowledge"], {"mode": "knowledge"}):
        with pytest.raises(RagModeError):
            resolve_rag_mode({RAG_MODE_CONTEXT_KEY: value})


def test_normalize_agrees_with_resolve() -> None:
    assert normalize_rag_mode(KNOWLEDGE_MODE) == KNOWLEDGE_MODE
    assert normalize_rag_mode(None) == GENERAL_MODE


def test_error_carries_value_code_and_expected_modes() -> None:
    error = RagModeError("auto")

    assert error.value == "auto"
    assert error.code == "invalid_rag_mode"
    assert error.expected == RAG_MODES
    assert isinstance(error, ValueError)
    assert GENERAL_MODE in str(error) and KNOWLEDGE_MODE in str(error)


def test_resolution_does_not_mutate_the_context() -> None:
    context = {RAG_MODE_CONTEXT_KEY: KNOWLEDGE_MODE}

    assert resolve_rag_mode(context) == KNOWLEDGE_MODE
    assert context == {RAG_MODE_CONTEXT_KEY: KNOWLEDGE_MODE}
