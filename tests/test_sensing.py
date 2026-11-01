import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l0 import L0Archive  # noqa: E402
from cether.perception import Perceiver  # noqa: E402
from cether.sensing import FirstRunNotice, SilentLearner, list_seen  # noqa: E402


def frame(bright: int) -> list[int]:
    return [10] * 32 + [10 + bright] * 32


class SensingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_silent_learning_off_writes_nothing(self) -> None:
        archive = L0Archive(self.tmp / "l0.jsonl")
        learner = SilentLearner(archive, enabled=False)
        self.assertIsNone(learner.observe("看到了东西", "screen"))
        self.assertEqual(list(archive), [])

    def test_silent_learning_on_writes_low_weight(self) -> None:
        archive = L0Archive(self.tmp / "l0.jsonl")
        learner = SilentLearner(archive, enabled=True)
        learner.observe("看到了东西", "screen")
        rows = list(archive)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["weight"], "low")

    def test_l0_rejects_unknown_weight(self) -> None:
        archive = L0Archive(self.tmp / "l0.jsonl")
        with self.assertRaises(ValueError):
            archive.append("x", "src", weight="high")

    def test_first_run_notice_shown_once(self) -> None:
        notice = FirstRunNotice(self.tmp / "flags" / "notice.flag")
        self.assertTrue(notice.due())
        notice.mark_shown()
        self.assertFalse(notice.due())

    def test_list_seen_returns_only_screen_changes(self) -> None:
        log = self.tmp / "world.jsonl"
        log.write_text(
            json.dumps({"tags": ["self_world"], "kind": "screen_change", "description": "a"}) + "\n"
            + json.dumps({"tags": ["other"], "kind": "screen_change", "description": "b"}) + "\n"
            + json.dumps({"tags": ["self_world"], "kind": "runtime", "description": "c"}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual([r["description"] for r in list_seen(log)], ["a"])

    def test_no_describer_logs_null_description(self) -> None:
        frames = [frame(0)]
        log = self.tmp / "world.jsonl"
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=None,
            world_log=log,
            foreground_app=lambda: "editor",
        )
        t = p.tick()
        self.assertTrue(t.changed)
        self.assertIsNone(t.description)
        self.assertEqual(p.model_calls, 0)
        self.assertIsNone(list_seen(log)[0]["description"])

    def test_look_now_describes_even_without_change(self) -> None:
        frames = [frame(0), frame(0)]
        log = self.tmp / "world.jsonl"
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=lambda: "手动看一眼",
            world_log=log,
            foreground_app=lambda: "editor",
        )
        p.tick()
        t = p.look_now()
        self.assertTrue(t.changed)
        self.assertEqual(t.description, "手动看一眼")

    def test_look_now_respects_pause(self) -> None:
        frames = [frame(0)]
        p = Perceiver(
            capture=lambda: frames.pop(0),
            describe=lambda: "x",
            world_log=self.tmp / "world.jsonl",
            foreground_app=lambda: "editor",
        )
        p.pause_capture()
        self.assertFalse(p.look_now().changed)
        self.assertEqual(len(frames), 1)


if __name__ == "__main__":
    unittest.main()
