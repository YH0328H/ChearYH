from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime


class DesktopRuntimeSleepTests(unittest.TestCase):
    def test_light_then_deep_sleep_runs_local_products_once(self):
        desktop = DesktopRuntime(Path(tempfile.mkdtemp()))
        role = desktop.registry.active
        self.assertIsNotNone(desktop.runtime.spatial_provider)
        self.assertEqual(desktop.runtime.spatial_provider.path, role.workspace / "memory" / "spatial-index.json")
        desktop.runtime.sleep_mode_provider = lambda _role, _now: "light"
        desktop.handle({"action": "send_message", "text": "routine topic detail"})
        service = desktop.runtime.sleep_provider.__self__
        calls = []
        service.index_update = lambda _role, ids: calls.append(tuple(ids)) or "updated"
        light = desktop.runtime.build_pipeline().tick()
        self.assertEqual(light.background_results["sleep_consolidation"]["mode"], "light")
        self.assertEqual(len(calls), 1)
        l1_path = role.workspace / "memory" / "l1.jsonl"
        self.assertFalse(l1_path.exists())

        desktop.runtime.sleep_mode_provider = lambda _role, _now: "deep"
        for text in ("dream fragment one", "dream fragment two", "dream fragment three"):
            service.l0.append(text, "test", "low")
        # Add role-local records without interrupting the scheduled deep sleep.
        service.l0.append("another project event", "test", "normal")
        service.l0.append("a third project event", "test", "normal")
        deep = desktop.runtime.build_pipeline().tick()
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(deep.background_results["reflection_calibration"]["narrative"])
        self.assertIn("indexed_candidates", deep.background_results["retrieval_bias_update"])
        records = [json.loads(line) for line in l1_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["emotion_tag"] for record in records}, {"reflection", "dream"})
        self.assertTrue(all(record["source_l0_ids"] for record in records))
        desktop.handle({"action": "shutdown"})


if __name__ == "__main__":
    unittest.main()
