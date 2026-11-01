import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.perception import Perceiver, average_hash, hamming  # noqa: E402


def frame(bright: int) -> list[int]:
    # 64 pixels: first half dark, second half bright, shifted by `bright`
    return [10] * 32 + [10 + bright] * 32


class PerceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "world.jsonl"
        self.frames: list[list[int]] = []
        self.describe_calls = 0

    def _describe(self) -> str:
        self.describe_calls += 1
        return "屏幕有变化"

    def _perceiver(self, app: str = "editor", **kwargs) -> Perceiver:
        return Perceiver(
            capture=lambda: self.frames.pop(0),
            describe=self._describe,
            world_log=self.log,
            foreground_app=lambda: app,
            **kwargs,
        )

    def test_first_frame_is_a_change(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver()
        t = p.tick()
        self.assertTrue(t.changed)
        self.assertEqual(p.model_calls, 1)

    def test_unchanged_screen_makes_zero_model_calls(self) -> None:
        self.frames = [frame(0), frame(0), frame(0)]
        p = self._perceiver()
        p.tick()
        calls_after_first = p.model_calls
        p.tick()
        p.tick()
        self.assertEqual(p.model_calls, calls_after_first)
        self.assertEqual(self.describe_calls, calls_after_first)

    def test_changed_screen_describes_and_logs(self) -> None:
        self.frames = [frame(0), frame(120)]
        p = self._perceiver()
        p.tick()
        t = p.tick()
        self.assertTrue(t.changed)
        self.assertEqual(p.model_calls, 2)
        rows = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["tags"], ["self_world"])
        self.assertEqual(rows[-1]["kind"], "screen_change")

    def test_paused_perception_does_not_capture(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver()
        p.pause_capture()
        t = p.tick()
        self.assertFalse(t.changed)
        self.assertEqual(len(self.frames), 1)  # capture was never called
        self.assertEqual(p.model_calls, 0)

    def test_raw_capture_is_not_retained(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver()
        p.tick()
        for name, value in vars(p).items():
            self.assertFalse(isinstance(value, list) and len(value) == 64, name)

    def test_denied_app_skips_capture(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver(app="banking", deny_apps=frozenset({"banking"}))
        t = p.tick()
        self.assertFalse(t.changed)
        self.assertEqual(len(self.frames), 1)
        self.assertEqual(p.model_calls, 0)

    def test_allowlist_excludes_other_apps(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver(app="chat", allow_apps=frozenset({"editor"}))
        self.assertFalse(p.tick().changed)
        self.assertEqual(len(self.frames), 1)

    def test_allowlist_permits_listed_app(self) -> None:
        self.frames = [frame(0)]
        p = self._perceiver(app="editor", allow_apps=frozenset({"editor"}))
        self.assertTrue(p.tick().changed)

    def test_resume_restores_capture(self) -> None:
        self.frames = [frame(0), frame(0)]
        p = self._perceiver()
        p.pause_capture()
        p.tick()
        p.resume_capture()
        self.assertTrue(p.tick().changed)

    def test_hash_distance(self) -> None:
        self.assertEqual(hamming(average_hash(frame(0)), average_hash(frame(0))), 0)
        self.assertGreater(hamming(average_hash(frame(0)), average_hash([10, 200] * 32)), 5)


if __name__ == "__main__":
    unittest.main()
