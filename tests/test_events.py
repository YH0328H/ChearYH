import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.events import RuntimeEvents  # noqa: E402
from cether.perception import Perceiver  # noqa: E402


def frame(bright: int) -> list[int]:
    return [10] * 32 + [10 + bright] * 32


class EventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = Path(tempfile.mkdtemp()) / "world.jsonl"

    def test_record_writes_self_world_tagged_line(self) -> None:
        ev = RuntimeEvents(self.log)
        self.assertTrue(ev.record("tool_timeout", "工具超时"))
        row = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["tags"], ["self_world"])
        self.assertEqual(row["kind"], "tool_timeout")

    def test_paused_events_write_nothing(self) -> None:
        ev = RuntimeEvents(self.log)
        ev.pause()
        self.assertFalse(ev.record("tool_timeout", "x"))
        self.assertFalse(self.log.exists())

    def test_resume_restores_events(self) -> None:
        ev = RuntimeEvents(self.log)
        ev.pause()
        ev.resume()
        self.assertTrue(ev.record("tool_timeout", "x"))

    def test_events_pause_does_not_stop_screen_capture(self) -> None:
        frames = [frame(0)]
        ev = RuntimeEvents(self.log)
        ev.pause()
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=None,
            world_log=Path(tempfile.mkdtemp()) / "screen.jsonl",
            foreground_app=lambda: "editor",
        )
        self.assertTrue(p.tick().changed)
        self.assertTrue(ev.paused)

    def test_screen_pause_does_not_stop_runtime_events(self) -> None:
        frames = [frame(0)]
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=None,
            world_log=Path(tempfile.mkdtemp()) / "screen.jsonl",
            foreground_app=lambda: "editor",
        )
        p.pause_capture()
        p.tick()
        self.assertTrue(RuntimeEvents(self.log).record("tool_timeout", "x"))


class ReleaseTests(unittest.TestCase):
    def test_release_runs_after_every_tick(self) -> None:
        released = []
        frames = [frame(0), frame(0)]
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=None,
            world_log=Path(tempfile.mkdtemp()) / "w.jsonl",
            foreground_app=lambda: "editor",
            release=lambda: released.append(1),
        )
        p.tick()
        p.tick()
        self.assertEqual(len(released), 2)

    def test_release_runs_even_when_capture_raises(self) -> None:
        released = []

        def boom():
            raise RuntimeError("capture failed")

        p = Perceiver(
            capture=boom,
            describe=None,
            world_log=Path(tempfile.mkdtemp()) / "w.jsonl",
            foreground_app=lambda: "editor",
            release=lambda: released.append(1),
        )
        with self.assertRaises(RuntimeError):
            p.tick()
        self.assertEqual(len(released), 1)


if __name__ == "__main__":
    unittest.main()
