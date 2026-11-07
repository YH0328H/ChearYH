from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime


def test_bootstrap_exposes_status_and_role_cards(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    payload = runtime.handle({"action": "bootstrap"})
    assert payload["active_role"]["name"] == "默认角色"
    assert payload["roles"][0]["active"] is True
    assert payload["view"]["status"]["sleep_status"] == "清醒"
    assert payload["view"]["status"]["mind_box"] == []
    runtime.handle({"action": "shutdown"})


def test_ui_actions_pause_capture_and_remember_are_visible(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    paused = runtime.handle({"action": "ui_action", "ui_action": "pause_capture", "payload": {"paused": True}})
    assert paused["accepted"] is True
    assert paused["payload"]["paused"] is True
    blocked = runtime.handle({"action": "ui_action", "ui_action": "look_now", "payload": {}})
    assert blocked["accepted"] is False
    assert blocked["feedback"]["status"] == "blocked"
    remembered = runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "用户喜欢夜空"}})
    assert remembered["accepted"] is True
    records = [json.loads(line) for line in (runtime.registry.active.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["tier_metadata"]["memory_tier"] == "high"
    runtime.handle({"action": "shutdown"})


def test_memory_timeline_returns_role_local_records(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "role local memory"}})
    page = runtime.handle({"action": "memory_timeline", "limit": 10})
    assert page["total"] == 1
    assert page["records"][0]["text"] == "role local memory"
    with pytest.raises(ValueError):
        runtime.handle({"action": "memory_timeline", "limit": 0})
    runtime.handle({"action": "shutdown"})


def test_role_switch_returns_progress_and_rebinds_ui(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    first = runtime.handle({"action": "bootstrap"})
    created = runtime.handle({"action": "create_role", "name": "工作角色"})
    switched = runtime.handle({"action": "switch_role", "role_id": first["active_role"]["role_id"]})
    assert switched["active_role"]["role_id"] == first["active_role"]["role_id"]
    assert len(switched["switch_progress"]) == 6
    assert switched["wake_pending"] is True
    assert created["active_role"]["name"] == "工作角色"
    runtime.handle({"action": "shutdown"})
