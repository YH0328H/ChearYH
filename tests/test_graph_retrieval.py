from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest

from cether.graph_retrieval import LocalCooccurrenceGraphProvider
from cether.retrieval import GraphRetrieval
from cether.roles import RoleRegistry


def _role(tmp_path: Path):
    registry = RoleRegistry(tmp_path / "roles.json")
    config = registry.create_role("Graph", tmp_path / "graph-workspace")
    registry.switch(config.role_id)
    return registry, registry.active


def test_builds_symmetric_role_local_cooccurrence_graph(tmp_path: Path) -> None:
    registry, role = _role(tmp_path)
    provider = LocalCooccurrenceGraphProvider(role, registry)

    graph = provider([
        {"id": "a", "text": "star map observe", "weight": "normal"},
        {"id": "b", "text": "star map record", "weight": "normal"},
    ])

    assert graph.get_node("star").doc_ids == ["a", "b"]
    assert [(edge.target, edge.weight) for edge in graph.get_neighbors("star")] == [("map", 2.0), ("observe", 1.0), ("record", 1.0)]
    results = GraphRetrieval(graph).search(["star"], top_k=4, max_hops=1)
    assert {result.doc_id for result in results} == {"a", "b"}


def test_provider_enforces_active_role_scope(tmp_path: Path) -> None:
    registry, role = _role(tmp_path)
    provider = LocalCooccurrenceGraphProvider(role, registry)
    other = registry.create_role("Other", tmp_path / "other-workspace")
    registry.switch(other.role_id)
    with pytest.raises(Exception, match="scope"):
        provider([])
