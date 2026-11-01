import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.runner import build_perceiver, run_loop  # noqa: E402
from cether.vision import VisionError  # noqa: E402

VISION_TOML = (
    '[vision]\n'
    'base_url = "https://x.test/v1"\n'
    'model_id = "m-1"\n'
    'key_env = "CETHER_TEST_KEY"\n'
)


def frame(bright: int) -> list[int]:
    return [10] * 32 + [10 + bright] * 32


def reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.vision = self.tmp / "vision.toml"
        self.vision.write_text(VISION_TOML, encoding="utf-8")
        self.log = self.tmp / "world.jsonl"

    def _build(self, grab_frames, post, app="editor"):
        grabs = list(grab_frames)
        return build_perceiver(
            vision_config_path=self.vision,
            world_log=self.log,
            environ={"CETHER_TEST_KEY": "k-test"},
            grab=lambda: grabs.pop(0),
            foreground_app=lambda: app,
            post=post,
        )

    def test_changed_frame_is_described_and_logged(self) -> None:
        sent = []

        def post(url, body, headers):
            sent.append((url, headers["Authorization"]))
            return reply("一个编辑器窗口")

        p, cfg = self._build([(frame(0), b"PNG-1")], post)
        t = p.tick()
        self.assertTrue(t.changed)
        self.assertEqual(t.description, "一个编辑器窗口")
        self.assertEqual(sent, [("https://x.test/v1/chat/completions", "Bearer k-test")])
        row = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["description"], "一个编辑器窗口")

    def test_describer_receives_the_same_frame_as_hashing(self) -> None:
        seen = []

        def post(url, body, headers):
            seen.append(body["messages"][0]["content"][1]["image_url"]["url"])
            return reply("ok")

        p, _ = self._build([(frame(0), b"PNG-SAME")], post)
        p.tick()
        import base64
        self.assertEqual(base64.b64decode(seen[0].split(",", 1)[1]), b"PNG-SAME")

    def test_unchanged_frame_makes_no_model_call(self) -> None:
        calls = []

        def post(url, body, headers):
            calls.append(1)
            return reply("x")

        p, _ = self._build([(frame(0), b"A"), (frame(0), b"B")], post)
        p.tick()
        p.tick()
        self.assertEqual(len(calls), 1)

    def test_describe_failure_does_not_block_logging_frame_result(self) -> None:
        def post(url, body, headers):
            raise VisionError("HTTP 500")

        p, _ = self._build([(frame(0), b"A")], post)
        with self.assertRaises(VisionError):
            p.tick()

    def test_run_loop_stops_at_max_ticks_and_sleeps_each_time(self) -> None:
        p, _ = self._build([(frame(0), b"A"), (frame(0), b"B"), (frame(0), b"C")],
                           lambda u, b, h: reply("x"))
        slept = []
        n = run_loop(p, 5.0, should_stop=lambda: False, sleep=slept.append, max_ticks=2)
        self.assertEqual(n, 2)
        self.assertEqual(slept, [5.0, 5.0])

    def test_run_loop_respects_stop_flag(self) -> None:
        p, _ = self._build([], lambda u, b, h: reply("x"))
        n = run_loop(p, 1.0, should_stop=lambda: True, sleep=lambda s: None)
        self.assertEqual(n, 0)

    def test_run_loop_rejects_non_positive_interval(self) -> None:
        p, _ = self._build([], lambda u, b, h: reply("x"))
        with self.assertRaises(ValueError):
            run_loop(p, 0, should_stop=lambda: True)


if __name__ == "__main__":
    unittest.main()
