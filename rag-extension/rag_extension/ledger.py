"""Run-scoped evidence ledger and app-scoped absorbed stats for extension stores."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING, Any

from rag_extension.contracts import Evidence, EvidenceLedgerEntry

if TYPE_CHECKING:
    from deerflow_extension_api import TaskOutcome


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class RagTaskLedger:
    """Run-scoped evidence ledger living in the extension task store.

    The host allocates one task store per lead/subagent execution when the
    extension registers a task-lifecycle contributor, and drops it when the run
    ends, so the ledger needs no cleanup of its own.
    """

    run_id: str | None = None
    entries: list[EvidenceLedgerEntry] = field(default_factory=list)
    searches: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def register_evidence(
        self,
        evidence: Sequence[Evidence],
        *,
        tool_call_id: str,
        retrieval_run_id: str | None,
        run_id: str | None = None,
    ) -> None:
        registered_at = _utc_now()
        with self._lock:
            if run_id is not None:
                self.run_id = run_id
            self.searches += 1
            self.entries.extend(
                EvidenceLedgerEntry(
                    evidence=item,
                    run_id=run_id if run_id is not None else (self.run_id or ""),
                    tool_call_id=tool_call_id,
                    retrieval_run_id=retrieval_run_id,
                    validation_status="valid",
                    registered_at=registered_at,
                )
                for item in evidence
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "searches": self.searches,
                "evidence_count": len(self.entries),
                "entries": [entry.to_dict() for entry in self.entries],
            }


@dataclass
class RagExtensionStats:
    """App-scoped totals absorbed from each finished run's ledger."""

    searches: int = 0
    evidence_registered: int = 0
    tasks: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def absorb(self, ledger: RagTaskLedger | None, outcome: TaskOutcome) -> None:
        with self._lock:
            if ledger is not None:
                with ledger._lock:
                    self.searches += ledger.searches
                    self.evidence_registered += len(ledger.entries)
            key = outcome.value
            self.tasks[key] = self.tasks.get(key, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "searches": self.searches,
                "evidence_registered": self.evidence_registered,
                "tasks": dict(self.tasks),
            }
