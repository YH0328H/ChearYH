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
from cether.desktop import DesktopRuntime
from cether.providers import (
    LocalRuleProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderError,
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

    def test_blank_message_rejected_without_provider_call(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.service.send("  ")
        self.assertEqual(self.provider.requests, [])


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.request = TurnRequest("A", "persona", "hello", {"social_battery": 0.8}, (), None)

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
