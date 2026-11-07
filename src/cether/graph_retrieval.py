"""Role-local deterministic co-occurrence graph construction for L0 retrieval."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .memory_retrieval import tokenize
from .retrieval import GraphEdge, GraphNode, KnowledgeGraph
from .roles import RoleContext, RoleRegistry


class LocalCooccurrenceGraphProvider:
    """Build a role-local graph from token co-occurrence in normal L0 records.

    Each token is a graph entity and each record contributes one document id to
    its node. Pair counts become directed edges with symmetric weights, allowing
    graph diffusion to expand a query seed into related role-local memories.
    """

    def __init__(self, role: RoleContext, registry: RoleRegistry) -> None:
        self.role = role
        self.registry = registry

    def __call__(self, records: list[dict[str, Any]]) -> KnowledgeGraph:
        """Return a deterministic graph for the supplied role-local records."""
        self.registry.ensure_role_scope(self.role.scope_id)
        node_docs: dict[str, set[str]] = {}
        pair_counts: Counter[tuple[str, str]] = Counter()
        for record in records:
            doc_id = str(record["id"])
            tokens = sorted(set(tokenize(str(record.get("text", "")))))
            for token in tokens:
                node_docs.setdefault(token, set()).add(doc_id)
            for index, source in enumerate(tokens):
                for target in tokens[index + 1:]:
                    pair_counts[(source, target)] += 1.0
                    pair_counts[(target, source)] += 1.0
        nodes = [GraphNode(token, token, sorted(doc_ids)) for token, doc_ids in sorted(node_docs.items())]
        edges = [GraphEdge(source, target, weight) for (source, target), weight in sorted(pair_counts.items())]
        return KnowledgeGraph(nodes, edges)
