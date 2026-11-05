from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.ui_contract import CONTEXT_MENU_ACTIONS, MAIN_NAVIGATION, RoleCardView, StatusView, UiAction, UiContract, memory_starfield


class UiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.role = RoleCardView("r1", "Mika", True, False, None, "calm", "C:/roles/mika", "resident")
        self.status = StatusView("tired", "sleeping", ("想说话",), "inside", "awake", "companion", "manual")
        self.capture = False
        self.events = False
        self.calls = []
        self.ui = UiContract(
            role_cards=lambda: (self.role, [self.role]),
            status=lambda: self.status,
            look_now=lambda: "scene",
            set_capture_paused=lambda value: setattr(self, "capture", value),
            set_events_paused=lambda value: setattr(self, "events", value),
            remember_this=lambda text: self.calls.append(("remember", text)) or "candidate-1",
            think_again=lambda memory_id: False,
            deepen=lambda memory_id: 0.9,
            switch_role=lambda role_id: type("Result", (), {"active_role_id": role_id, "error": None})(),
            memory_page=lambda cursor, limit: ([{"id": "m1"}], None, 1),
            clock=lambda: datetime(2026, 11, 5, tzinfo=timezone.utc),
        )

    def test_app_view_exposes_role_and_status_snapshot(self) -> None:
        view = self.ui.app_view()
        self.assertEqual(view.active_role.name, "Mika")
        self.assertEqual(view.status.gate_reason, "sleeping")
        self.assertFalse(view.perception_paused)

    def test_perception_and_runtime_event_pause_are_independent(self) -> None:
        self.ui.dispatch(UiAction.PAUSE_CAPTURE, {"paused": True})
        self.assertTrue(self.capture)
        self.assertFalse(self.events)
        self.ui.dispatch(UiAction.PAUSE_RUNTIME_EVENTS, {"paused": True})
        self.assertTrue(self.events)
        self.assertTrue(self.ui.app_view().perception_paused)
        self.assertTrue(self.ui.app_view().events_paused)

    def test_look_now_returns_feedback(self) -> None:
        result = self.ui.dispatch(UiAction.LOOK_NOW)
        self.assertTrue(result.accepted)
        self.assertEqual(result.feedback.message, "已看一眼")
        self.assertEqual(result.payload["result"], "scene")

    def test_remember_this_acknowledges_submission(self) -> None:
        result = self.ui.dispatch(UiAction.REMEMBER_THIS, {"text": "用户喜欢夜空"})
        self.assertEqual(result.feedback.status, "submitted")
        self.assertEqual(result.feedback.message, "已提交")
        self.assertEqual(self.calls, [("remember", "用户喜欢夜空")])

    def test_think_again_has_changed_and_unchanged_feedback(self) -> None:
        result = self.ui.dispatch(UiAction.THINK_AGAIN, {"memory_id": "m1"})
        self.assertEqual(result.feedback.message, "暂时没变")

    def test_deepen_returns_weight_feedback(self) -> None:
        result = self.ui.dispatch(UiAction.DEEPEN, {"memory_id": "m1"})
        self.assertEqual(result.payload["weight"], 0.9)

    def test_memory_timeline_is_paginated_and_validates_limit(self) -> None:
        page = self.ui.memory_timeline(limit=10)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.records[0]["id"], "m1")
        with self.assertRaises(ValueError):
            self.ui.memory_timeline(limit=0)

    def test_archive_and_restore_actions_return_explicit_choices(self) -> None:
        archive = self.ui.dispatch(UiAction.ARCHIVE_MEMORY, {"memory_id": "m1"})
        restore = self.ui.dispatch(UiAction.RESTORE_MEMORY, {"memory_id": "m1"})
        self.assertIn("move_to_cold", archive.payload["choices"])
        self.assertIn("inject_once", restore.payload["choices"])

    def test_callback_error_is_visible_as_inline_feedback(self) -> None:
        ui = UiContract(role_cards=lambda: (self.role, [self.role]), status=lambda: self.status,
                        look_now=lambda: (_ for _ in ()).throw(RuntimeError("camera unavailable")))
        result = ui.dispatch(UiAction.LOOK_NOW)
        self.assertFalse(result.accepted)
        self.assertEqual(result.feedback.message, "camera unavailable")
        self.assertIn("camera unavailable", ui.app_view().inline_notices)

    def test_starfield_projection_is_deterministic_and_keeps_visual_attributes(self) -> None:
        nodes = [{"memory_id": "m1", "room": 1, "slot_id": 2, "room_capacity": 10,
                  "weight": 0.8, "category": "relation", "connections": [("m2", 0.6)]}]
        first = memory_starfield(nodes)
        second = memory_starfield(nodes)
        self.assertEqual(first, second)
        self.assertEqual(first[0].category, "relation")
        self.assertEqual(first[0].connections, (("m2", 0.6),))
        self.assertGreater(first[0].x, 0)
        self.assertGreater(first[0].y, 0)

    def test_navigation_and_context_menu_are_explicit_contracts(self) -> None:
        self.assertIn("roles", [item.key for item in MAIN_NAVIGATION])
        self.assertIn("settings", [item.key for item in MAIN_NAVIGATION])
        self.assertIn(UiAction.LOOK_NOW, CONTEXT_MENU_ACTIONS)
        self.assertNotIn(UiAction.SWITCH_ROLE, CONTEXT_MENU_ACTIONS)

    def test_forget_and_restore_choices_have_contract_feedback(self) -> None:
        forget = self.ui.dispatch(UiAction.ARCHIVE_MEMORY, {"memory_id": "m1"})
        self.assertIn("不推荐", forget.payload["delete_warning"])
        accepted = self.ui.dispatch(UiAction.RESTORE_MEMORY, {"memory_id": "m1", "choice": "inject_once"})
        self.assertTrue(accepted.payload["storage_unchanged"])

    def test_look_now_is_blocked_when_capture_paused(self) -> None:
        self.ui.dispatch(UiAction.PAUSE_CAPTURE, {"paused": True})
        result = self.ui.dispatch(UiAction.LOOK_NOW)
        self.assertFalse(result.accepted)
        self.assertEqual(result.feedback.status, "blocked")

    def test_starfield_rejects_invalid_canvas_size(self) -> None:
        with self.assertRaises(ValueError):
            memory_starfield([], width=0)


if __name__ == "__main__":
    unittest.main()
