from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.roles import RoleRegistry, ScopeMismatchError
from cether.spatial_retrieval import SpatialMemoryProvider


class SpatialMemoryProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.registry = RoleRegistry(self.tmp / "registry.json")
        role_cfg = self.registry.create_role("A", self.tmp / "a")
        self.registry.create_role("B", self.tmp / "b")
        self.registry.switch(role_cfg.role_id)
        self.role = self.registry.active
        self.records = [
            {"id": "high-a", "weight": 0.9, "text": "重要关系 生日 庆祝"},
            {"id": "high-b", "weight": 0.9, "text": "重要关系 旅行 回忆"},
        ]

    def test_returns_fixed_route_query_matches_and_persists_assignments(self) -> None:
        provider = SpatialMemoryProvider(self.role, self.registry)
        results = provider("生日 回忆", self.records)
        self.assertEqual([item.doc_id for item in results], ["high-a", "high-b"])
        saved = json.loads(provider.path.read_text(encoding="utf-8"))
        self.assertEqual(set(saved["assignments"]), {"high-a", "high-b"})
        restored = SpatialMemoryProvider(self.role, self.registry)
        self.assertEqual(restored.index.patrol_route(), provider.index.patrol_route())

    def test_nonmatching_query_returns_no_high_memories(self) -> None:
        provider = SpatialMemoryProvider(self.role, self.registry)
        self.assertEqual(provider("unrelated xyz", self.records), [])

    def test_scope_mismatch_is_rejected(self) -> None:
        provider = SpatialMemoryProvider(self.role, self.registry)
        other = self.registry.list_roles()[1]
        self.registry.switch(other.role_id)
        with self.assertRaises(ScopeMismatchError):
            provider("birthday", self.records)


if __name__ == "__main__":
    unittest.main()
