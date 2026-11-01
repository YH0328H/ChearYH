import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.wake import WakeState  # noqa: E402

CLOSED = datetime(2026, 11, 1, 20, 0)


class WakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp()) / "wake"
        self.state = WakeState(self.dir)

    def test_no_snapshot_means_nothing_pending(self) -> None:
        self.assertIsNone(self.state.pending(CLOSED))

    def test_pending_reports_gap_and_snapshot(self) -> None:
        self.state.save_snapshot({"mood": "calm"}, CLOSED)
        p = self.state.pending(CLOSED + timedelta(hours=3))
        self.assertEqual(p.gap_seconds, 3 * 3600)
        self.assertEqual(p.snapshot, {"mood": "calm"})

    def test_consumed_injection_is_not_repeated(self) -> None:
        self.state.save_snapshot({"k": 1}, CLOSED)
        self.state.mark_consumed()
        self.assertIsNone(self.state.pending(CLOSED + timedelta(hours=1)))

    def test_unconsumed_injection_survives_switch_away(self) -> None:
        # Wake happened, but the user never spoke before switching away.
        self.state.save_snapshot({"k": 1}, CLOSED)
        self.assertIsNotNone(self.state.pending(CLOSED + timedelta(minutes=5)))
        self.assertIsNotNone(self.state.pending(CLOSED + timedelta(hours=2)))

    def test_new_close_makes_injection_pending_again(self) -> None:
        self.state.save_snapshot({"k": 1}, CLOSED)
        self.state.mark_consumed()
        self.state.save_snapshot({"k": 2}, CLOSED + timedelta(hours=1))
        p = self.state.pending(CLOSED + timedelta(hours=2))
        self.assertEqual(p.snapshot, {"k": 2})

    def test_mark_consumed_without_snapshot_is_noop(self) -> None:
        self.state.mark_consumed()
        self.assertIsNone(self.state.pending(CLOSED))

    def test_save_leaves_no_temp_file(self) -> None:
        self.state.save_snapshot({"k": 1}, CLOSED)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["wake.json"])


class RenderTests(unittest.TestCase):
    def test_format_gap_units(self) -> None:
        from cether.wake import format_gap
        self.assertEqual(format_gap(30), "不到一分钟")
        self.assertEqual(format_gap(5 * 60), "5 分钟")
        self.assertEqual(format_gap(3 * 3600 + 10 * 60), "3 小时 10 分钟")
        self.assertEqual(format_gap(2 * 86400), "2 天")
        self.assertEqual(format_gap(86400 + 5 * 3600), "1 天 5 小时")

    def test_render_includes_gap_and_snapshot(self) -> None:
        from cether.wake import WakePayload, render_injection
        text = render_injection(WakePayload(gap_seconds=3600, snapshot={"心情": "平静"}))
        self.assertIn("1 小时", text)
        self.assertIn("心情: 平静", text)


if __name__ == "__main__":
    unittest.main()
