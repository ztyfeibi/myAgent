"""Task lifecycle: allocate the run-scoped evidence ledger and absorb stats at run end."""

from __future__ import annotations

from deerflow_extension_api import ExtensionData, TaskInfo, TaskOutcome

from rag_extension.ledger import RagExtensionStats, RagTaskLedger


class RagTaskLifecycle:
    """Allocate one :class:`RagTaskLedger` per lead/subagent execution.

    Registering this contributor makes the host allocate the extension task
    store for every run, which ``knowledge_search`` then uses as the run-scoped
    evidence ledger; finished runs are absorbed into app-scoped totals.
    """

    async def on_task_start(
        self,
        app_store: ExtensionData,
        task_store: ExtensionData,
        info: TaskInfo,
    ) -> None:
        task_store.set(RagTaskLedger(run_id=info.run_id))

    async def on_task_stop(
        self,
        app_store: ExtensionData,
        task_store: ExtensionData,
        info: TaskInfo,
        outcome: TaskOutcome,
    ) -> None:
        ledger = task_store.remove(RagTaskLedger)
        app_store.get_or_init(RagExtensionStats, RagExtensionStats).absorb(ledger, outcome)
