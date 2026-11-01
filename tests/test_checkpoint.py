import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.checkpoint import MindBox, Outcome, run_checkpoint  # noqa: E402
from cether.window import load_window_config  # noqa: E402

NOW = datetime(2026, 11, 1, 20, 0)
THRESHOLD = load_window_config(ROOT / "config" / "window.toml")[0].impulse_threshold


def go(box, **overrides):
    kwargs = dict(
        now=NOW,
        expression_impulse=0.9,
        impulse_threshold=THRESHOLD,
        gate_reason=None,
        hesitation_resolution=None,
        mind_box=box,
        hesitation_text="犹豫内容",
    )
    kwargs.update(overrides)
    return run_checkpoint(**kwargs)


class CheckpointTests(unittest.TestCase):
    def test_low_impulse_blocks_without_writing_mind_box(self):
        box = MindBox()
        r = go(box, expression_impulse=THRESHOLD - 0.01)
        self.assertEqual((r.outcome, r.reason), (Outcome.BLOCKED, "low_impulse"))
        self.assertEqual(box.items, [])

    def test_impulse_at_threshold_passes(self):
        self.assertEqual(go(MindBox(), expression_impulse=THRESHOLD).outcome, Outcome.WITHDRAWN)

    def test_gate_reason_blocks(self):
        r = go(MindBox(), gate_reason="busy")
        self.assertEqual((r.outcome, r.reason), (Outcome.BLOCKED, "busy"))

    def test_spoke_does_not_write_mind_box(self):
        box = MindBox()
        r = go(box, hesitation_resolution=Outcome.SPOKE)
        self.assertEqual(r.outcome, Outcome.SPOKE)
        self.assertEqual(box.items, [])

    def test_withdrawn_soft_and_unresolved_write_mind_box(self):
        box = MindBox()
        self.assertEqual(go(box, hesitation_resolution=Outcome.WITHDRAWN).outcome, Outcome.WITHDRAWN)
        self.assertEqual(go(box, hesitation_resolution=Outcome.SOFT).outcome, Outcome.SOFT)
        self.assertEqual(go(box, hesitation_resolution=None).outcome, Outcome.WITHDRAWN)
        self.assertEqual(len(box.pending_hesitation()), 3)


if __name__ == "__main__":
    unittest.main()
