from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.conversation import ConversationService
from cether.backchannel import BackchannelScheduler
from cether.desktop import DesktopRuntime
from cether.providers import (
    LocalRuleProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderError,
    ExpressionDirective,
    TurnRequest,
    TurnResponse,
)
from cether.roles import RoleRegistry, ScopeMismatchError
from cether.runtime_services import RuntimeServices
from cether.trigger import TriggerConfig
from cether.wake import WakeState


class StubProvider:
    def __init__(self, response=None, error=None):
        self.response = response or TurnResponse("收到", "short", "warm")
        self.error = error
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.registry = RoleRegistry(self.tmp / "registry.json", clock=lambda: self.now)
        self.one = self.registry.create_role("Alpha", self.tmp / "alpha")
        self.two = self.registry.create_role("Beta", self.tmp / "beta")
        self.registry.switch(self.one.role_id)
        self.provider = StubProvider()
        self.service = self._service(self.registry.active, self.provider)

    def _service(self, role, provider):
        runtime = RuntimeServices(
            role=role, registry=self.registry, trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: None, decision=lambda _request: None, expression=lambda _d, _r: None,
            clock=lambda: self.now,
        )
        return ConversationService(role=role, registry=self.registry, runtime=runtime,
                                   provider=provider, clock=lambda: self.now)

    def test_structured_expression_directive_survives_conversation_serialization(self):
        self.provider.response = TurnResponse(
            "难过只是文本线索",
            "full",
            "neutral",
            ExpressionDirective("joyful", "smile", "nod"),
        )
        turn = self.service.send("庆祝一下")
        self.assertEqual(turn.directive, {"tone": "joyful", "expression": "smile", "action": "nod"})
        self.assertEqual(self.service.history()[-1]["directive"], turn.directive)
        self.assertEqual(turn.resolved_expression["emotion"], "joyful")
        self.assertEqual(turn.resolved_expression["expression"], "smile")
        self.assertEqual(turn.resolved_expression["action"], "nod")

    def test_backchannel_is_cancelled_before_provider_returns_and_never_persists(self):
        from threading import Event
        case = next(item for item in json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))["cases"]
                    if item["id"] == "conversation.backchannel.cancel")
        delivered = Event()
        handles = []
        provider_started = Event()
        provider_release = Event()
        class BlockingProvider(StubProvider):
            def respond(inner_self, request):
                provider_started.set()
                self.assertTrue(provider_release.wait(2))
                return super(BlockingProvider, inner_self).respond(request)
        def deliver(handle):
            handles.append(handle)
            delivered.set()
        service = self._service(self.registry.active, BlockingProvider())
        service.backchannel = BackchannelScheduler(deliver)

        from threading import Thread
        result = []
        worker = Thread(target=lambda: result.append(service.send(case["input"]["text"])))
        worker.start()
        self.assertTrue(provider_started.wait(1))
        self.assertTrue(delivered.wait(1))
        self.assertFalse(handles[0].may_enqueue_tts())
        provider_release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        turn = result[0]
        self.assertEqual(turn.text, "收到")
        self.assertTrue(delivered.is_set())
        self.assertEqual(len(handles), 1)
        self.assertFalse(handles[0].may_enqueue_tts())
        rows = [json.loads(line) for line in (self.one.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["text"] for row in rows], ["谢谢你", "收到"])
        self.assertEqual([item["role"] for item in service.history()], ["user", "assistant"])

    def test_backchannel_none_for_unmatched_utterance(self):
        started = []
        scheduler = BackchannelScheduler(lambda handle: started.append(handle))
        self.assertIsNone(scheduler.start("just a normal statement"))
        self.assertEqual(started, [])

    def test_send_persists_history_l0_and_expression_feedback(self):
        self.service._l0.append("用户偏爱茉莉花茶", "conversation")
        self.service._l0.append("今天稍微有些疲惫", "conversation")
        turn = self.service.send("你还记得我喜欢什么茶吗？")
        self.assertEqual(turn.text, "收到")
        self.assertEqual(self.provider.requests[0].recent_memories, ("用户偏爱茉莉花茶",))
        history = self.service.history()
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        l0 = (self.one.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(l0), 4)
        self.assertEqual([json.loads(line)["text"] for line in l0[-2:]], ["你还记得我喜欢什么茶吗？", "收到"])
        state = json.loads((self.one.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["dimensions"]["emotional_residue"], "warm")
        self.assertAlmostEqual(state["dimensions"]["social_battery"], 0.75)

    def test_provider_failure_does_not_consume_wake_or_persist_turn(self):
        WakeState(self.one.workspace).save_snapshot({"topic": "pending"}, self.now)
        service = self._service(self.registry.active, StubProvider(error=ProviderError("offline")))
        with self.assertRaisesRegex(ProviderError, "offline"):
            service.send("retry me")
        self.assertIsNotNone(self.registry.pending_wake(self.one.role_id))
        self.assertEqual(service.history(), [])

    def test_retrieval_provider_failure_returns_reply_without_memory_injection(self):
        self.service._l0.append("蓝色鲸鱼记忆命中词", "conversation")
        self.service.retrieval.embedding_provider = lambda _texts: (_ for _ in ()).throw(RuntimeError("embedding offline"))

        turn = self.service.send("鲸鱼记忆命中词")

        self.assertEqual(turn.text, "收到")
        self.assertEqual(self.provider.requests[-1].recent_memories, ())
        self.assertIn("RuntimeError: embedding offline", self.service.retrieval.last_observation.error)
        self.assertEqual([row["role"] for row in self.service.history()], ["user", "assistant"])
        l0_rows = [json.loads(line) for line in (self.one.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["text"] for row in l0_rows[-2:]], ["鲸鱼记忆命中词", "收到"])

    def test_vector_scoring_failure_does_not_return_lexical_memory(self):
        from unittest.mock import patch

        case = next(item for item in json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))["cases"] if item["id"] == "retrieval.vector.failure")
        self.service._l0.append(case["input"]["memory"], "conversation")
        self.service.retrieval.embedding_provider = lambda texts: [[1.0, 0.0] for _ in texts]
        with patch("cether.memory_retrieval.VectorRetrieval.search", side_effect=RuntimeError(case["input"]["provider_error"])):
            turn = self.service.send(case["input"]["query"])

        self.assertEqual(turn.text, "收到")
        self.assertEqual(self.provider.requests[-1].recent_memories, ())
        self.assertEqual(self.service.retrieval.last_observation.channel, "none")
        self.assertIn(f"RuntimeError: {case['input']['provider_error']}", self.service.retrieval.last_observation.error)
        self.assertTrue(case["expected"]["reply_continues"])
        self.assertFalse(case["expected"]["memories_injected"])
        self.assertFalse(case["expected"]["lexical_fallback"])
        self.assertTrue(case["expected"]["error_observable"])
        self.assertEqual([row["role"] for row in self.service.history()], ["user", "assistant"])

    def test_graph_provider_failure_does_not_fallback_to_lexical_memory(self):
        corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
        case = next(item for item in corpus["cases"] if item["id"] == "retrieval.graph.failure")
        self.service._l0.append(case["input"]["memory"], "conversation")
        error = case["input"]["provider_error"]
        self.service.retrieval.graph_provider = lambda _records: (_ for _ in ()).throw(RuntimeError(error))

        turn = self.service.send(case["input"]["query"])

        self.assertTrue(case["expected"]["reply_continues"])
        self.assertEqual(turn.text, "收到")
        self.assertEqual(self.provider.requests[-1].recent_memories, ())
        self.assertFalse(case["expected"]["memories_injected"])
        self.assertFalse(case["expected"]["lexical_fallback"])
        observation = self.service.retrieval.last_observation
        self.assertEqual(observation.channel, "none")
        self.assertTrue(case["expected"]["error_observable"])
        self.assertIn(f"RuntimeError: {error}", observation.error)
        self.assertEqual([row["role"] for row in self.service.history()], ["user", "assistant"])

    def test_wake_is_injected_once_and_consumed_after_provider_success(self):
        WakeState(self.one.workspace).save_snapshot({"topic": "pending"}, self.now)
        provider = StubProvider()
        service = self._service(self.registry.active, provider)
        service.send("hello")
        self.assertIn("pending", provider.requests[0].wake_context)
        self.assertIsNone(self.registry.pending_wake(self.one.role_id))
        service.send("again")
        self.assertIsNone(provider.requests[1].wake_context)

    def test_role_scope_blocks_old_conversation_after_switch(self):
        self.registry.switch(self.two.role_id)
        with self.assertRaises(ScopeMismatchError):
            self.service.send("must not cross roles")
        self.assertFalse((self.two.workspace / "conversation.jsonl").exists())

    def test_corpus_scope_mismatch_rejects_before_read_or_fallback(self):
        case = next(
            item for item in json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))["cases"]
            if item["id"] == "retrieval.scope.mismatch"
        )
        from unittest.mock import patch

        read_attempts = []
        def tracked_iter(_archive):
            read_attempts.append(True)
            return iter(())

        self.registry.switch(self.two.role_id)
        with patch("cether.l0.L0Archive.__iter__", tracked_iter), self.assertRaises(ScopeMismatchError):
            self.service.send(case["input"]["query"])

        self.assertTrue(case["expected"]["rejected"])
        self.assertFalse(case["expected"]["fallback"])
        self.assertFalse(case["expected"]["archive_read"])
        self.assertFalse(case["expected"]["reply_written"])
        self.assertEqual(read_attempts, [])
        self.assertFalse((self.two.workspace / "conversation.jsonl").exists())
        self.assertEqual(self.provider.requests, [])

    def test_role_self_awareness_and_boundaries_reach_only_own_provider_context(self):
        aware = self.registry.create_role("Aware", self.tmp / "aware", self_awareness="semi_aware")
        (aware.workspace / "persona.md").write_text("温柔但有边界。", encoding="utf-8")
        (aware.workspace / "self_awareness.md").write_text("我知道自己会在应用关闭时暂停。", encoding="utf-8")
        (aware.workspace / "boundaries.md").write_text("不要替用户决定私人事务。", encoding="utf-8")
        self.registry.switch(aware.role_id)
        service = self._service(self.registry.active, self.provider)
        service.send("你是谁？")
        request = self.provider.requests[-1]
        self.assertEqual(request.self_awareness, "semi_aware")
        self.assertIn("角色自我认知档位（由用户角色卡设定）：semi_aware", request.persona)
        self.assertIn("我知道自己会在应用关闭时暂停。", request.persona)
        self.assertIn("不要替用户决定私人事务。", request.persona)

        self.registry.switch(self.two.role_id)
        other = StubProvider()
        self._service(self.registry.active, other).send("你是谁？")
        self.assertEqual(other.requests[-1].self_awareness, "resident")
        self.assertNotIn("应用关闭时暂停", other.requests[-1].persona)
        self.assertNotIn("私人事务", other.requests[-1].persona)

    def test_blank_message_rejected_without_provider_call(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.service.send("  ")
        self.assertEqual(self.provider.requests, [])


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.request = TurnRequest("A", "persona", "hello", {"social_battery": 0.8}, (), None)

    def test_structured_expression_directive_precedes_text_inference_and_missing_falls_back(self):
        from cether.cognition import resolve_expression

        corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
        case = next(item for item in corpus["cases"] if item["id"] == "expression.structured.precedence")
        explicit = resolve_expression({**case["input"], "kind": "full"})
        self.assertTrue(case["expected"]["directive_precedes_inference"])
        self.assertEqual((explicit.tone, explicit.emotion, explicit.expression, explicit.action),
                         (case["input"]["directive"]["tone"], case["input"]["directive"]["tone"],
                          case["input"]["directive"]["expression"], case["input"]["directive"]["action"]))
        fallback = resolve_expression(case["expected"]["fallback_input"])
        self.assertTrue(case["expected"]["missing_directive_falls_back"])
        self.assertEqual(fallback.emotion, case["expected"]["fallback_emotion"])
        self.assertIsNone(fallback.expression)

    def test_http_adapter_parses_structured_expression_directive(self):
        import cether.providers as providers
        original = providers.urllib.request.urlopen
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self):
                return json.dumps({"choices": [{"message": {
                    "content": "answer",
                    "expression_directive": {"tone": "warm", "expression": "smile", "action": "nod"},
                }}]}).encode()
        providers.urllib.request.urlopen = lambda _req, timeout: Response()
        import os
        os.environ["CETHER_TEST_ADAPTER_KEY"] = "test-secret"
        try:
            result = OpenAICompatibleProvider(ProviderConfig(key_env="CETHER_TEST_ADAPTER_KEY")).respond(self.request)
        finally:
            os.environ.pop("CETHER_TEST_ADAPTER_KEY", None)
            providers.urllib.request.urlopen = original
        self.assertEqual(result.directive, ExpressionDirective("warm", "smile", "nod"))

    def test_local_provider_is_operational_without_network(self):
        result = LocalRuleProvider().respond(self.request)
        self.assertIn("hello", result.text)
        self.assertEqual(result.kind, "short")

    def test_http_adapter_formats_request_and_parses_response(self):
        seen = {}
        def post(_url, _body, _headers):
            return {"choices": [{"message": {"content": "  answer  "}}]}
        # Exercise adapter transport deterministically by replacing urllib's opener.
        import cether.providers as providers
        original = providers.urllib.request.urlopen
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self): return json.dumps(post("", {}, {})).encode()
        providers.urllib.request.urlopen = lambda req, timeout: (seen.update(url=req.full_url, headers=dict(req.header_items()), timeout=timeout) or Response())
        import os
        os.environ["CETHER_TEST_ADAPTER_KEY"] = "test-secret"
        try:
            result = OpenAICompatibleProvider(ProviderConfig("https://example.test/v1", "model", "CETHER_TEST_ADAPTER_KEY", 2)).respond(self.request)
        finally:
            os.environ.pop("CETHER_TEST_ADAPTER_KEY", None)
            providers.urllib.request.urlopen = original
        self.assertEqual(result.text, "answer")
        self.assertEqual(seen["timeout"], 2)

    def test_missing_remote_key_is_explicit(self):
        import os
        old = os.environ.pop("CETHER_TEST_KEY", None)
        try:
            with self.assertRaisesRegex(ProviderError, "CETHER_TEST_KEY"):
                OpenAICompatibleProvider(ProviderConfig(key_env="CETHER_TEST_KEY")).respond(self.request)
        finally:
            if old is not None:
                os.environ["CETHER_TEST_KEY"] = old

    def test_config_validates_timeout_and_temperature(self):
        with self.assertRaises(ValueError):
            ProviderConfig(timeout_seconds=0)
        with self.assertRaises(ValueError):
            ProviderConfig(temperature=3)


class DesktopBridgeTests(unittest.TestCase):
    def test_desktop_binds_concrete_local_decision_and_expression_providers(self):
        runtime = DesktopRuntime(Path(tempfile.mkdtemp()))
        self.assertIsNotNone(runtime.runtime)
        self.assertEqual(type(runtime.runtime.decision_provider).__name__, "method")
        decision = runtime.runtime.decision_provider({"state": {"social_battery": 0.8,
                                                                      "expression_impulse": 0.5}})
        expression = runtime.runtime.expression_provider(decision, {"context": None})
        self.assertTrue(decision.speak)
        self.assertEqual(expression.text, "我在听。")
        self.assertIsNotNone(runtime.runtime.sleep_provider)
        self.assertIsNotNone(runtime.runtime.reflection_provider)
        runtime.handle({"action": "shutdown"})

    def test_bootstrap_create_switch_and_chat_are_role_scoped(self):
        runtime = DesktopRuntime(Path(tempfile.mkdtemp()))
        first = runtime.handle({"action": "bootstrap"})
        self.assertEqual(sum(role["active"] for role in first["roles"]), 1)
        created = runtime.handle({"action": "create_role", "name": "Second"})
        self.assertEqual(created["active_role"]["name"], "Second")
        role2 = created["active_role"]["role_id"]
        runtime.handle({"action": "send_message", "text": "isolated"})
        role1 = first["active_role"]["role_id"]
        switched = runtime.handle({"action": "switch_role", "role_id": role1})
        self.assertEqual(switched["history"], [])
        self.assertEqual(switched["active_role"]["role_id"], role1)
        runtime.handle({"action": "switch_role", "role_id": role2})
        self.assertEqual(len(runtime.handle({"action": "bootstrap"})["history"]), 2)


if __name__ == "__main__":
    unittest.main()
