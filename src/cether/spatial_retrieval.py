"""Role-local fixed-route retrieval adapter for explicitly high-weight L0 items."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .memory_retrieval import tokenize
from .retrieval import RetrievalResult
from .roles import RoleContext, RoleRegistry
from .spatial import SpatialIndex


class SpatialMemoryProvider:
    """Maintain a persistent fixed-route index and return query-activated slots.

    The spatial index supplies stable route order; lexical overlap is only the
    activation signal, not a semantic embedding or graph score.
    """

    def __init__(self, role: RoleContext, registry: RoleRegistry, index: SpatialIndex | None = None) -> None:
        self.role = role
        self.registry = registry
        self.path = role.workspace / "memory" / "spatial-index.json"
        self.index = index or SpatialIndex.load(self.path)

    def __call__(self, query: str, records: list[dict[str, Any]]) -> list[RetrievalResult]:
        """Return high-tier query matches in deterministic room/slot patrol order."""
        self.registry.ensure_role_scope(self.role.scope_id)
        query_terms = set(tokenize(query))
        by_id = {str(record["id"]): record for record in records}
        for memory_id in by_id:
            if self.index.slot_of(memory_id) is None:
                self.index.assign(memory_id)
        self.index.save(self.path)

        results: list[RetrievalResult] = []
        for _slot, memory_id in self.index.patrol_route():
            if memory_id is None or memory_id not in by_id:
                continue
            text = str(by_id[memory_id].get("text", ""))
            overlap = len(query_terms & set(tokenize(text)))
            if overlap:
                results.append(RetrievalResult(memory_id, float(overlap)))
        return results
