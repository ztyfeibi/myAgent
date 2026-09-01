"""RAG extension for DeerFlow: explicit knowledge/general modes and a stub evidence loop."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_extension_api import ExtensionInstall, ExtensionRegistry, extension

from rag_extension.lifecycle import RagTaskLifecycle

__all__ = ["install"]


@extension(api="0.2.0", name="rag-extension")
def install(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None:
    """Register the RAG extension's task-lifecycle contributions.

    The mode-gating middleware is intentionally not registered here: isolated
    plugin-contributed middlewares cannot substitute model requests, so
    ``KnowledgeModeMiddleware`` must be declared through the operator-trusted
    ``extensions.middlewares`` config entry instead. See the package README.
    """
    if config.get("enabled", True) is False:
        return
    registry.task_lifecycle(RagTaskLifecycle())


_entry_point: ExtensionInstall = install
