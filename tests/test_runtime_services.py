from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.roles import RoleRegistry
from cether.runtime_services import FeedbackConfig, RuntimeServices
from cether.trigger import TriggerConfig


class RuntimeServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.registry = RoleRegistry(self.tmp / "registry.json", clock=lambda: self.now)
        self.role = self.registry.create_role("A", self.tmp / "role")
        self.registry.switch(self.role.role_id)
        self.role_context = self.registry.active
        self.metadata = {"theme": "work", "salience": 0.1, "emotion_intensity": 0.1}
        self.services = RuntimeServices(
            role=self.role_context, registry=self.registry,
            trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: {"description": "changed scene", "changed": True},
            event_metadata=lambda _event: self.metadata,
            decision=lambda request: {"action": "speak"},
            expression=lambda decision, request: {"kind": "short", "emotion": "calm"},
            clock=lambda: self.now,
        )

    def test_pipeline_persists_l0_state_and_expression_feedback(self):
        context = self.services.build_pipeline().tick()
        self.assertIsNotNone(context.l0_id)
        self.assertTrue((self.role.workspace / "memory" / "l0.jsonl").exists())
        state = json.loads((self.role.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(state["dimensions"]["social_battery"], 0.75)
        self.assertEqual(state["dimensions"]["emotional_residue"], "calm")

    def test_explicit_trigger_without_narrative_provider_does_not_write_l1(self):
        self.metadata["salience"] = 0.9
        context = self.services.build_pipeline().tick()
        self.assertTrue(context.trigger)
        self.assertIsNone(context.narrative)
        self.assertFalse((self.role.workspace / "memory" / "l1.jsonl").exists())

    def test_repetition_trigger_and_narrative_provider_write_tagged_l1(self):
        from cether.narrative import NarrativeConfig

        responses = iter(['{"narrative":"重复主题叙事","emotion_tag":"calm","relation_tag":"user"}'] * 2)
        post = lambda *_args: {"choices": [{"message": {"content": next(responses)}}]}
        service = RuntimeServices(
            role=self.role_context, registry=self.registry,
            trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: {"description": "重复主题内容", "changed": True},
            event_metadata=lambda _event: {"theme": "same", "salience": 0.1},
            decision=lambda _request: None, expression=lambda _d, _r: {"kind": "short"},
            narrative_config=NarrativeConfig("https://provider.test/v1", "model", "key"),
            narrative_post=post, clock=lambda: self.now,
        )
        first = service.build_pipeline().tick()
        second = service.build_pipeline().tick()
        self.assertFalse(first.trigger)
        self.assertTrue(second.trigger)
        records = (self.role.workspace / "memory" / "l1.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(records), 1)
        self.assertIn('"emotion_tag": "calm"', records[0])

    def test_unchanged_observation_skips_decision_and_expression(self):
        calls = []
        self.services.perception_provider = lambda: {"description": None, "changed": False}
        self.services.decision_provider = lambda request: calls.append("decision")
        self.services.expression_provider = lambda decision, request: calls.append("expression")
        context = self.services.build_pipeline().tick()
        self.assertIsNone(context.l0_id)
        self.assertFalse((self.role.workspace / "memory" / "l0.jsonl").exists())
        self.assertEqual(context.state["social_battery"], 0.8)
        self.assertEqual(self.services._state.timestamp, self.now.timestamp())
        self.assertEqual(calls, [])

    def test_gate_blocks_before_archive_and_model_providers(self):
        calls = []
        self.services.gate_reason_provider = lambda _role, _event: "quiet hours"
        self.services.decision_provider = lambda request: calls.append("decision")
        self.services.expression_provider = lambda decision, request: calls.append("expression")
        events = []
        context = self.services.build_pipeline(event_sink=events.append).tick()
        self.assertIsNone(context.l0_id)
        self.assertEqual(calls, [])
        self.assertIn(("gate", "blocked", "quiet hours"), [(e.stage, e.status, e.detail) for e in events])

    def test_wake_context_is_consumed_once_on_user_turn(self):
        from cether.wake import WakeState

        WakeState(self.role.workspace).save_snapshot({"topic": "pending"}, self.now)
        service = RuntimeServices(
            role=self.role_context, registry=self.registry,
            trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: {"description": "unused", "changed": True},
            decision=lambda request: None,
            expression=lambda _decision, _request: None,
            clock=lambda: self.now,
        )
        self.assertIsNotNone(self.registry.pending_wake(self.role.role_id))
        seen = []
        service.decision_provider = lambda request: seen.append(request.get("wake_context")) or {"action": "listen"}
        service.build_pipeline().tick()
        self.assertIsNotNone(self.registry.pending_wake(self.role.role_id))
        self.assertEqual(seen, [None])
        result = service.decide_user_turn(None, service._state)
        self.assertEqual(result, {"action": "listen"})
        self.assertIn("pending", seen[1])
        self.assertIsNone(service.begin_user_turn())
        self.assertIsNone(self.registry.pending_wake(self.role.role_id))
        service.close()

    def test_soft_refusal_has_configured_recovery(self):
        self.services.expression_provider = lambda decision, request: {"kind": "soft_refusal", "emotion": "calm"}
        self.services.feedback_config = FeedbackConfig(0.1, 0.05, 0.02)
        self.services.build_pipeline().tick()
        state = json.loads((self.role.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(state["dimensions"]["social_battery"], 0.82)

    def test_sleep_freezes_foreground_and_skips_expression(self):
        calls = []
        self.services.sleep_mode_provider = lambda _role, _now: "deep"
        self.services.decision_provider = lambda _request: calls.append("decision")
        self.services.expression_provider = lambda _d, _r: calls.append("expression")
        before = dict(self.services._state.dimensions)
        context = self.services.build_pipeline().tick()
        self.assertEqual(context.perception, {"sleeping": True, "sleep_mode": "deep"})
        self.assertEqual(calls, [])
        self.assertEqual(self.services._state.dimensions, before)

    def test_sleep_mode_prevents_perception_and_routes_sleep_work(self):
        calls = []
        self.services.sleep_mode_provider = lambda _role, _now: "light"
        self.services.sleep_provider = lambda _role, state: calls.append(("sleep", state)) or {"merged": 1}
        self.services.reflection_provider = lambda _role, state: calls.append(("reflection", state))
        self.services.retrieval_index_provider = lambda _role: calls.append(("index",))
        context = self.services.build_pipeline().tick()
        self.assertEqual(context.perception, {"sleeping": True, "sleep_mode": "light"})
        self.assertEqual([item[0] for item in calls], ["sleep"])

    def test_deep_sleep_calibrates_baseline_writes_reflection_and_bias(self):
        self.services.sleep_mode_provider = lambda _role, _now: "deep"
        self.services.sleep_provider = lambda _role, _state: {"deep": True}
        self.services.reflection_provider = lambda _role, _state: {
            "baseline": {"self_baseline": 0.72}, "narrative": "自我反思", "retrieval_bias": {"relation": 1.2}
        }
        self.services.retrieval_index_provider = lambda _role: {"sleep_index": 0.9}
        context = self.services.build_pipeline().tick()
        self.assertEqual(context.perception["sleep_mode"], "deep")
        state = json.loads((self.role.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["dimensions"]["self_baseline"], 0.72)
        l1 = (self.role.workspace / "memory" / "l1.jsonl").read_text(encoding="utf-8")
        self.assertIn("自我反思", l1)
        bias = json.loads((self.role.workspace / "retrieval_bias.json").read_text(encoding="utf-8"))
        self.assertEqual(bias, {"sleep_index": 0.9})
        seen = []
        self.services.sleep_mode_provider = lambda _role, _now: "awake"
        self.services.decision_provider = lambda request: seen.append(request["retrieval_bias"]) or None
        self.services.build_pipeline().tick()
        self.assertEqual(seen, [{"sleep_index": 0.9}])

    def test_feedback_reloads_after_service_restart(self):
        self.services.build_pipeline().tick()
        self.services.close()
        restarted = RuntimeServices(
            role=self.role_context, registry=self.registry,
            trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: {"description": "x", "changed": True},
            decision=lambda _request: None, expression=lambda _d, _r: {"kind": "full"},
            clock=lambda: self.now,
        )
        self.assertAlmostEqual(restarted._state.dimensions["social_battery"], 0.75)
        restarted.close()

    def test_close_disallows_pipeline_rebuild(self):
        self.services.build_pipeline()
        self.services.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.services.build_pipeline()

    def test_wrong_scope_blocks_persistence(self):
        other = self.registry.create_role("B", self.tmp / "other")
        self.registry.switch(other.role_id)
        with self.assertRaises(Exception):
            self.services.build_pipeline().tick()
        self.assertFalse((self.role.workspace / "memory" / "l0.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
