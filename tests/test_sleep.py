from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l0 import L0Archive
from cether.roles import RoleRegistry
from cether.sleep import SleepConfig, SleepService, load_sleep_config


class SleepServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        self.registry = RoleRegistry(self.tmp / "roles.json", clock=lambda: self.now)
        cfg = self.registry.create_role("A", self.tmp / "role")
        self.registry.switch(cfg.role_id)
        self.role = self.registry.active
        self.archive = L0Archive(self.role.workspace / "memory" / "l0.jsonl")
        self.service = SleepService(self.role, self.registry, clock=lambda: self.now)

    def test_light_sleep_deduplicates_candidates_without_rewriting_l0(self):
        first = self.archive.append("shared topic detail", "test", "normal")
        self.archive.append("shared topic detail", "test", "normal")
        self.archive.append("unrelated unique note", "test", "normal")
        before = (self.role.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8")
        result = self.service.consolidate(self.role, {})
        after = (self.role.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result["candidate_ids"], [first, result["candidate_ids"][1]])
        self.assertEqual(before, after)
        self.assertEqual(result["distinct_records"], 2)

    def test_deep_products_are_traceable_and_calibrate_state(self):
        ids = [self.archive.append(text, "test", "low") for text in (
            "work project detail", "work project progress", "work project outcome")]
        result = self.service.reflect(self.role, {"focus_baseline": 0.5})
        dream = self.service.deep_sleep(self.role, {})
        l1_path = self.role.workspace / "memory" / "l1.jsonl"
        # The service emits products; RuntimeServices owns their L1 persistence.
        entries = [json.loads(line) for line in l1_path.read_text(encoding="utf-8").splitlines()] if l1_path.exists() else []
        self.assertEqual(result["baseline"]["focus_baseline"], 0.45)
        self.assertEqual(result["source_l0_ids"], ids)
        self.assertEqual(entries[0]["emotion_tag"], "dream")
        self.assertEqual(entries[0]["source_l0_ids"], ids)
        self.assertEqual(dream["source_l0_ids"], ids)

    def test_scope_mismatch_is_rejected_and_empty_archive_is_noop(self):
        empty = self.service.reflect(self.role, {})
        self.assertIsNone(empty["narrative"])
        other = self.registry.create_role("B", self.tmp / "other")
        self.registry.switch(other.role_id)
        with self.assertRaises(Exception):
            self.service.consolidate(self.role, {})

    def test_config_load_and_validation(self):
        self.assertEqual(load_sleep_config(ROOT / "config" / "sleep.toml").baseline_alpha, 0.1)
        with self.assertRaises(ValueError):
            SleepConfig(duplicate_similarity=2)


if __name__ == "__main__":
    unittest.main()
