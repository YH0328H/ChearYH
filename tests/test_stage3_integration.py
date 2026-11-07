from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime
from cether.l0 import L0Archive
from cether.roles import RoleRegistry
from cether.ui_contract import UiAction


def test_perception_notice_seen_and_independent_pauses(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    view = runtime.handle({"action": "bootstrap"})["view"]
    assert view["first_run_notice_due"] is True
    acknowledged = runtime.handle({"action": "ui_action", "ui_action": UiAction.ACKNOWLEDGE_PERCEPTION.value})
    assert acknowledged["accepted"] is True
    assert acknowledged["view"]["first_run_notice_due"] is False

    runtime.handle({"action": "ui_action", "ui_action": UiAction.PAUSE_CAPTURE.value, "payload": {"paused": True}})
    runtime.handle({"action": "ui_action", "ui_action": UiAction.PAUSE_RUNTIME_EVENTS.value, "payload": {"paused": False}})
    view = runtime.handle({"action": "bootstrap"})["view"]
    assert view["perception_paused"] is True
    assert view["events_paused"] is False
    look = runtime.handle({"action": "ui_action", "ui_action": UiAction.LOOK_NOW.value})
    assert look["accepted"] is False


def test_memory_lifecycle_and_diary_are_role_local_and_append_only(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.handle({"action": "ui_action", "ui_action": UiAction.REMEMBER_THIS.value,
                    "payload": {"text": "remember this important fact"}})
    record = list(L0Archive(runtime.registry.active.workspace / "memory" / "l0.jsonl"))[-1]
    raw_before = (runtime.registry.active.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8")
    archived = runtime.handle({"action": "ui_action", "ui_action": UiAction.ARCHIVE_MEMORY.value,
                               "payload": {"memory_id": record["id"], "choice": "move_to_cold"}})
    assert archived["accepted"] is True
    assert runtime._lifecycle.excluded_ids() == frozenset({record["id"]})
    assert (runtime.registry.active.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8") == raw_before
    restored = runtime.handle({"action": "ui_action", "ui_action": UiAction.RESTORE_MEMORY.value,
                               "payload": {"memory_id": record["id"], "choice": "inject_once"}})
    assert restored["accepted"] is True
    assert runtime._consume_injections()[0]["id"] == record["id"]


def test_role_actions_and_mode_are_exposed_by_desktop_runtime(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    role_id = runtime.registry.active.config.role_id
    extra = runtime.registry.create_role("Second", tmp_path / "second")
    assert runtime.handle({"action": "set_mode", "mode": "work"}) == {
        "mode": "work", "source": "manual", "override": "work"
    }
    assert runtime.handle({"action": "role_archive", "role_id": extra.role_id})["archived"] is True
    assert runtime.handle({"action": "role_restore", "role_id": extra.role_id})["archived"] is False
    exported = tmp_path / "role.cether-role"
    assert runtime.handle({"action": "role_export", "role_id": role_id, "destination": str(exported)})["package"] == str(exported)


def test_role_package_includes_owned_memory_and_wakes_on_import(tmp_path: Path) -> None:
    registry = RoleRegistry(tmp_path / "roles.json")
    source = registry.create_role("Source", tmp_path / "source")
    registry.switch(source.role_id)
    L0Archive(source.workspace / "memory" / "l0.jsonl").append("owned memory", "test")
    package = tmp_path / "source.cether-role"
    registry.export_package(source.role_id, package)
    with __import__("zipfile").ZipFile(package) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("package.json"))
    assert "memory/l0.jsonl" in names
    assert "global_channels" in manifest["excluded"]

    target = registry.create_role("Target", tmp_path / "target")
    registry.switch(target.role_id)
    imported = registry.import_package(package, tmp_path / "imported", conflict="rename", renamed_to="Imported")
    assert (imported.workspace / "memory" / "l0.jsonl").exists()
    assert registry.pending_wake(imported.role_id) is not None
