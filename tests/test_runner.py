import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.runner import (  # noqa: E402
    RuntimeConfig,
    RuntimePipeline,
    RuntimeSteps,
    build_perceiver,
    run_loop,
)
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


class FakeScopeGuard:
    def __init__(self, active="role-a"):
        self.active = active
        self.checks = []

    def ensure_role_scope(self, scope_id):
        self.checks.append(scope_id)
        if scope_id != self.active:
            raise RuntimeError("scope mismatch")


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

    def _pipeline(self, calls, *, trigger=True, scope=None, background=None):
        def step(name, value=None):
            def run(*args):
                calls.append(name)
                if name == "should_trigger_l1":
                    return trigger
                if name == "sleep_consolidation" and isinstance(background, Exception):
                    raise background
                return value if value is not None else name
            return run

        steps = RuntimeSteps(
            perceive=step("perceive", {"event": "screen", "sleep_mode": "deep" if background is not None else "awake", "sleeping": False}),
            append_l0=step("append_l0", "l0-1"),
            should_trigger_l1=step("should_trigger_l1"),
            generate_l1=step("generate_l1", {"narrative": "story"}),
            update_state=step("update_state", {"mood": 0.2}),
            decide=step("decide", {"speak": True}),
            express=step("express", "hello"),
            feed_result=step("feed_result", "fed"),
            sleep_consolidation=step("sleep_consolidation", "consolidated") if background is not None else None,
            reflection_calibration=step("reflection_calibration", "reflected") if background is not None else None,
            retrieval_bias_update=step("retrieval_bias_update", "biased") if background is not None else None,
        )
        return RuntimePipeline(
            role_scope="role-a", scope_guard=scope or FakeScopeGuard(), steps=steps,
            config=RuntimeConfig(interval_seconds=0.25),
        )

    def test_pipeline_runs_foreground_stages_in_contract_order(self) -> None:
        calls = []
        context = self._pipeline(calls).tick()
        self.assertEqual(calls, [
            "perceive", "append_l0", "should_trigger_l1", "generate_l1", "update_state",
            "decide", "express", "feed_result",
        ])
        self.assertEqual(context.l0_id, "l0-1")
        self.assertEqual(context.narrative, {"narrative": "story"})
        self.assertEqual(context.result, "fed")

    def test_pipeline_unchanged_observation_updates_state_but_skips_models(self) -> None:
        calls = []
        steps = RuntimeSteps(
            perceive=lambda: {"description": None, "changed": False},
            append_l0=lambda _event: None,
            should_trigger_l1=lambda *_args: calls.append("trigger") or True,
            generate_l1=lambda *_args: calls.append("l1"),
            update_state=lambda *_args: calls.append("state") or {"updated": True},
            decide=lambda *_args: calls.append("decision"),
            express=lambda *_args: calls.append("expression"),
            feed_result=lambda *_args: calls.append("feedback"),
        )
        context = RuntimePipeline(role_scope="role-a", scope_guard=FakeScopeGuard(), steps=steps).tick()
        self.assertEqual(calls, ["state"])
        self.assertEqual(context.state, {"updated": True})
        self.assertFalse(context.trigger)
        self.assertIsNone(context.decision)
        self.assertIsNone(context.expression)

    def test_pipeline_skips_l1_without_explicit_trigger(self) -> None:
        calls = []
        context = self._pipeline(calls, trigger=False).tick()
        self.assertNotIn("generate_l1", calls)
        self.assertIsNone(context.narrative)
        self.assertIn("update_state", calls)

    def test_pipeline_rechecks_role_scope_for_every_stage(self) -> None:
        calls = []
        guard = FakeScopeGuard()
        pipeline = self._pipeline(calls, scope=guard)
        pipeline.tick()
        self.assertEqual(len(guard.checks), len(calls) + 1)
        self.assertTrue(all(scope == "role-a" for scope in guard.checks))

    def test_pipeline_scope_failure_blocks_all_domain_work(self) -> None:
        calls = []
        guard = FakeScopeGuard(active="role-b")
        with self.assertRaisesRegex(RuntimeError, "scope mismatch"):
            self._pipeline(calls, scope=guard).tick()
        self.assertEqual(calls, [])

    def test_background_failures_are_recorded_without_failing_tick(self) -> None:
        calls = []
        context = self._pipeline(calls, background=RuntimeError("sleep store unavailable")).tick()
        self.assertEqual(context.result, "fed")
        self.assertIsNone(context.background_results["sleep_consolidation"])
        pipeline = self._pipeline([], background=RuntimeError("sleep store unavailable"))
        context = pipeline.tick()
        self.assertTrue(any(e.stage == "sleep_consolidation" and e.status == "error" for e in pipeline._events))

    def test_run_honors_max_ticks_and_sleeps_only_between_ticks(self) -> None:
        calls = []
        slept = []
        report = self._pipeline(calls).run(max_ticks=2, sleep=slept.append)
        self.assertEqual(report.ticks, 2)
        self.assertEqual(report.stopped_reason, "max_ticks")
        self.assertEqual(slept, [0.25])

    def test_stop_request_prevents_future_ticks(self) -> None:
        calls = []
        pipeline = self._pipeline(calls)
        pipeline.stop()
        report = pipeline.run(max_ticks=2, sleep=lambda _s: None)
        self.assertEqual(report.ticks, 0)
        with self.assertRaisesRegex(RuntimeError, "runtime is stopping"):
            pipeline.tick()

    def test_cancel_waits_for_active_tick_and_prevents_late_domain_work(self) -> None:
        import threading
        import time

        entered = threading.Event()
        release = threading.Event()
        calls = []
        def perceive():
            entered.set()
            release.wait(2)
            return {"event": "screen"}
        steps = RuntimeSteps(
            perceive=perceive,
            append_l0=lambda _e: calls.append("l0"),
            should_trigger_l1=lambda *_a: False,
            generate_l1=lambda *_a: None,
            update_state=lambda *_a: calls.append("state"),
            decide=lambda *_a: None,
            express=lambda *_a: None,
            feed_result=lambda *_a: None,
        )
        pipeline = RuntimePipeline(role_scope="role-a", scope_guard=FakeScopeGuard(), steps=steps)
        worker = threading.Thread(target=pipeline.tick)
        worker.start()
        self.assertTrue(entered.wait(1))
        result = []
        canceller = threading.Thread(target=lambda: result.append(pipeline.cancel(timeout=2)))
        canceller.start()
        time.sleep(0.02)
        release.set()
        worker.join(2)
        canceller.join(2)
        self.assertEqual(result, [True])
        self.assertEqual(calls, ["l0", "state"])

    def test_rejects_overlapping_ticks(self) -> None:
        calls = []
        pipeline = self._pipeline(calls)
        pipeline._stage_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, "concurrent runtime ticks"):
                pipeline.tick()
        finally:
            pipeline._stage_lock.release()


if __name__ == "__main__":
    unittest.main()
