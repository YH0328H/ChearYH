from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.roles import RoleError, RoleRegistry, ScopeMismatchError


class Hooks:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_load = False
        self.fail_rollback = False

    def persist(self, role): self.calls.append(f"persist:{role.config.role_id}")
    def cancel_and_persist_tasks(self, role): self.calls.append(f"cancel:{role.config.role_id}")
    def release_resources(self, role): self.calls.append(f"release:{role.config.role_id}")
    def load(self, role):
        self.calls.append(f"load:{role.config.role_id}")
        if self.fail_load:
            self.fail_load = False
            raise RuntimeError("broken target config")
    def activate(self, role, wake): self.calls.append(f"activate:{role.config.role_id}")
    def rollback(self, role):
        self.calls.append(f"rollback:{role.config.role_id}")
        if self.fail_rollback:
            raise RuntimeError("rollback broke")


class RoleRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.hooks = Hooks()
        self.registry = RoleRegistry(self.tmp / "registry.json", hooks=self.hooks)
        self.one = self.registry.create_role("Alpha", self.tmp / "alpha")
        self.two = self.registry.create_role("Beta", self.tmp / "beta")
        self.registry.switch(self.one.role_id)

    def test_roles_have_separate_workspace_artifact_roots(self) -> None:
        self.assertTrue((self.one.workspace / "roles").is_dir())
        self.assertTrue((self.one.workspace / "artifacts").is_dir())
        self.assertNotEqual(self.one.workspace, self.two.workspace)

    def test_scope_mismatch_raises_without_fallback(self) -> None:
        with self.assertRaises(ScopeMismatchError):
            self.registry.ensure_role_scope(self.two.role_id)
        self.assertEqual(self.registry.active.config.role_id, self.one.role_id)

    def test_switch_progress_order_and_active_role(self) -> None:
        events = []
        registry = RoleRegistry(self.tmp / "other.json", hooks=self.hooks, progress=events.append)
        a = registry.create_role("A", self.tmp / "a")
        b = registry.create_role("B", self.tmp / "b")
        registry.switch(a.role_id)
        result = registry.switch(b.role_id)
        self.assertEqual(result.active_role_id, b.role_id)
        self.assertEqual([event.completed for event in events], [1, 2, 3, 4, 5, 6])
        self.assertEqual(len({r.role_id for r in registry.list_roles()}), 2)

    def test_switch_issues_pending_wake_and_consumes_on_first_turn_only(self) -> None:
        self.registry.switch(self.two.role_id)
        (self.one.workspace / "state.json").write_text('{"mood":"steady"}', encoding="utf-8")
        result = self.registry.switch(self.one.role_id)
        self.assertIsNotNone(result.wake)
        self.assertEqual(result.wake.snapshot["role_id"], self.one.role_id)
        self.registry.mark_first_turn_consumed(self.one.role_id)
        self.assertIsNone(self.registry._wake_for(self.one))

    def test_failed_target_load_rolls_back_active_role(self) -> None:
        self.hooks.fail_load = True
        result = self.registry.switch(self.two.role_id)
        self.assertEqual(result.active_role_id, self.one.role_id)
        self.assertIn("broken target config", result.error)
        self.assertEqual(self.registry.active.config.role_id, self.one.role_id)
        self.assertIn(f"rollback:{self.one.role_id}", self.hooks.calls)

    def test_failed_rollback_enters_read_only_error_state(self) -> None:
        self.hooks.fail_load = True
        self.hooks.fail_rollback = True
        with self.assertRaises(RoleError):
            self.registry.switch(self.two.role_id)
        self.assertTrue(self.registry.read_only_error)
        with self.assertRaises(RoleError):
            self.registry.ensure_role_scope(self.one.role_id)

    def test_invalid_state_is_rejected_and_old_role_remains_active(self) -> None:
        (self.two.workspace / "state.json").write_text("[]", encoding="utf-8")
        result = self.registry.switch(self.two.role_id)
        self.assertIsNotNone(result.error)
        self.assertEqual(self.registry.active.config.role_id, self.one.role_id)

    def test_archive_restore_and_two_step_delete(self) -> None:
        archived = self.registry.archive(self.two.role_id)
        self.assertTrue(archived.archived)
        self.assertNotIn(self.two.role_id, [r.role_id for r in self.registry.list_roles()])
        self.registry.restore(self.two.role_id)
        with self.assertRaises(RoleError):
            self.registry.delete_archived(self.two.role_id, confirmations=1)
        self.registry.archive(self.two.role_id)
        self.registry.delete_archived(self.two.role_id, confirmations=2)
        self.assertFalse(self.two.workspace.exists())

    def test_workspace_snapshot_restores_complete_unit_after_restart(self) -> None:
        (self.one.workspace / "state.json").write_text('{"dimensions":{"battery":0.4}}', encoding="utf-8")
        (self.one.workspace / "mind_box.json").write_text('["thought"]', encoding="utf-8")
        (self.one.workspace / "candidates.json").write_text('[{"draft":"pending"}]', encoding="utf-8")
        self.registry.switch(self.two.role_id)
        (self.one.workspace / "state.json").write_text('{"dimensions":{"battery":0.1}}', encoding="utf-8")
        restarted = RoleRegistry(self.tmp / "registry.json", hooks=Hooks())
        self.assertEqual(json.loads((self.one.workspace / "state.json").read_text(encoding="utf-8")), {"dimensions": {"battery": 0.4}})
        self.assertEqual(json.loads((self.one.workspace / "mind_box.json").read_text(encoding="utf-8")), ["thought"])
        self.assertEqual(json.loads((self.one.workspace / "candidates.json").read_text(encoding="utf-8")), [{"draft": "pending"}])
        self.assertEqual(restarted.active.config.role_id, self.two.role_id)

    def test_cancel_timeout_rolls_back_without_switching_active_role(self) -> None:
        callbacks = []
        self.registry.register_task_canceller(self.one.role_id, lambda: False)
        result = self.registry.switch(self.two.role_id)
        self.assertEqual(self.registry.active.config.role_id, self.one.role_id)
        self.assertIn("timed out", result.error)
        self.assertIn(f"rollback:{self.one.role_id}", self.hooks.calls)

    def test_workspace_snapshot_checksum_failure_fails_closed(self) -> None:
        self.registry.switch(self.two.role_id)
        snap = next((self.one.workspace / "snapshots").glob("*.json"))
        snap.write_text("corrupt", encoding="utf-8")
        with self.assertRaisesRegex(Exception, "checksum"):
            RoleRegistry(self.tmp / "registry.json", hooks=Hooks())

    def test_registered_pipeline_is_cancelled_before_role_release(self) -> None:
        from cether.runtime_services import RuntimeServices
        from cether.trigger import TriggerConfig

        services = RuntimeServices(
            role=self.registry.active, registry=self.registry,
            trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: "event", decision=lambda _request: None,
            expression=lambda _decision, _request: None,
        )
        pipeline = services.build_pipeline()
        self.registry.switch(self.two.role_id)
        self.assertTrue(pipeline.stop_requested)

    def test_import_package_conflict_requires_explicit_rename_and_preserves_existing_role(self) -> None:
        package = self.registry.export_package(self.one.role_id, self.tmp / "alpha.zip")
        existing_workspace = self.one.workspace
        existing_role_id = self.one.role_id
        target = self.tmp / "imported-alpha"

        with self.assertRaisesRegex(RoleError, "role name conflict requires rename or replace"):
            self.registry.import_package(package, target, conflict="reject")

        self.assertEqual(self.registry.active.config.role_id, existing_role_id)
        self.assertTrue(existing_workspace.is_dir())
        self.assertFalse(target.exists())
        self.assertEqual(len(self.registry.list_roles()), 2)

        imported = self.registry.import_package(
            package, target, conflict="rename", renamed_to="Alpha Imported"
        )
        self.assertEqual(imported.name, "Alpha Imported")
        self.assertTrue((target / "role.json").is_file())
        self.assertEqual(len(self.registry.list_roles()), 3)

    def test_workspace_binding_requires_existing_directory_and_clean_or_role_marker(self) -> None:
        with self.assertRaises(RoleError):
            self.registry.create_role("Missing", self.tmp / "missing", bind_existing=True)
        dirty = self.tmp / "dirty"
        dirty.mkdir()
        (dirty / "notes.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(RoleError):
            self.registry.create_role("Dirty", dirty, bind_existing=True)


if __name__ == "__main__":
    unittest.main()
