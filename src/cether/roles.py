"""Global single-active role registry, scope enforcement, lifecycle and role packages.

This module is the backend contract for TASK.md chapter 9. Every role owns an
independent workspace. Switching is transactional: persist the current role,
load and validate the target, then publish it as active; any failure restores
the previous active context. Non-active roles remain frozen on disk.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from .wake import WakePayload, WakeState

MAX_ROLES = 5
ROLE_CARD_FILES = (
    "persona.md",
    "boundaries.md",
    "appearance.json",
    "expression.json",
    "window.toml",
    "checkpoint.toml",
)


class RoleError(RuntimeError):
    """Base error for role operations."""


class ScopeMismatchError(RoleError):
    """Raised when an operation's role scope differs from the active role."""


class RoleLoadError(RoleError):
    """Raised when a role workspace or its persisted state is invalid."""


class RoleHooks(Protocol):
    """Runtime integration points; each hook must finish before switch advances."""

    def persist(self, role: RoleContext) -> None: ...
    def cancel_and_persist_tasks(self, role: RoleContext) -> None: ...
    def release_resources(self, role: RoleContext) -> None: ...
    def load(self, role: RoleContext) -> None: ...
    def activate(self, role: RoleContext, wake: WakePayload | None) -> None: ...
    def rollback(self, role: RoleContext) -> None: ...


@dataclass(frozen=True)
class RoleConfig:
    role_id: str
    name: str
    workspace: Path
    created_at: str
    archived: bool = False
    self_awareness: str = "resident"
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.role_id or not self.name.strip():
            raise ValueError("role_id and name must be non-empty")
        if self.self_awareness not in {"resident", "semi_aware", "fully_aware"}:
            raise ValueError("self_awareness must be resident, semi_aware, or fully_aware")


@dataclass(frozen=True)
class RoleContext:
    config: RoleConfig
    scope_id: str

    @property
    def workspace(self) -> Path:
        return self.config.workspace


@dataclass(frozen=True)
class SwitchProgress:
    step: str
    completed: int
    total: int = 6
    message: str = ""


@dataclass(frozen=True)
class SwitchResult:
    active_role_id: str
    wake: WakePayload | None
    progress: tuple[SwitchProgress, ...]
    error: str | None = None


class _NullHooks:
    def persist(self, role: RoleContext) -> None: pass
    def cancel_and_persist_tasks(self, role: RoleContext) -> None: pass
    def release_resources(self, role: RoleContext) -> None: pass
    def load(self, role: RoleContext) -> None: pass
    def activate(self, role: RoleContext, wake: WakePayload | None) -> None: pass
    def rollback(self, role: RoleContext) -> None: pass


class RoleRegistry:
    """Own the global active-role pointer and role lifecycle."""

    def __init__(
        self,
        registry_path: Path,
        *,
        hooks: RoleHooks | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        progress: Callable[[SwitchProgress], None] | None = None,
    ) -> None:
        self._path = registry_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._hooks = hooks or _NullHooks()
        self._clock = clock
        self._progress_callback = progress or (lambda _event: None)
        self._roles: dict[str, RoleConfig] = {}
        self._active_id: str | None = None
        self._read_only_error = False
        self._switch_lock = threading.RLock()
        if registry_path.exists():
            self._load_registry()

    @property
    def active(self) -> RoleContext | None:
        if self._active_id is None:
            return None
        cfg = self._roles[self._active_id]
        return RoleContext(cfg, cfg.role_id)

    @property
    def read_only_error(self) -> bool:
        return self._read_only_error

    def list_roles(self, *, include_archived: bool = False) -> list[RoleConfig]:
        return sorted(
            (r for r in self._roles.values() if include_archived or not r.archived),
            key=lambda r: (r.name.casefold(), r.role_id),
        )

    def create_role(
        self,
        name: str,
        workspace: Path,
        *,
        role_id: str | None = None,
        self_awareness: str = "resident",
        bind_existing: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> RoleConfig:
        if len([r for r in self._roles.values() if not r.archived]) >= MAX_ROLES:
            raise RoleError(f"role limit reached ({MAX_ROLES})")
        if any(r.name.casefold() == name.casefold() and not r.archived for r in self._roles.values()):
            raise RoleError(f"role name already exists: {name}")
        if bind_existing:
            if not workspace.is_dir():
                raise RoleError("existing workspace directory does not exist")
            if any(workspace.iterdir()) and not (workspace / "role.json").exists():
                raise RoleError("workspace is non-empty and is not a CetherYH role")
        else:
            workspace.mkdir(parents=True, exist_ok=False)
        cfg = RoleConfig(
            role_id=role_id or uuid.uuid4().hex,
            name=name,
            workspace=workspace.resolve(),
            created_at=self._clock().isoformat(),
            self_awareness=self_awareness,
            metadata=metadata or {},
        )
        if cfg.role_id in self._roles:
            raise RoleError(f"role id already exists: {cfg.role_id}")
        cfg.workspace.mkdir(parents=True, exist_ok=True)
        for directory in ("memory", "state", "mind_box", "candidates", "snapshots", "roles", "artifacts"):
            (cfg.workspace / directory).mkdir(exist_ok=True)
        self._write_role_config(cfg)
        self._roles[cfg.role_id] = cfg
        self._save_registry()
        return cfg

    def ensure_role_scope(self, scope_id: str) -> RoleContext:
        """Reject missing, archived or cross-role scopes without fallback."""
        active = self.active
        if self._read_only_error:
            raise RoleError("role registry is in read-only error state")
        if active is None:
            raise RoleError("no active role")
        if scope_id != active.scope_id:
            raise ScopeMismatchError(f"scope mismatch: expected {active.scope_id!r}, got {scope_id!r}")
        return active

    def switch(self, target_id: str) -> SwitchResult:
        """Switch roles with ordered progress and rollback on every failed step.

        A registry-local lock serializes transitions so there is never more
        than one in-flight role activation within this process.
        """
        with self._switch_lock:
            return self._switch_locked(target_id)

    def _switch_locked(self, target_id: str) -> SwitchResult:
        if self._read_only_error:
            raise RoleError("role registry is in read-only error state")
        target = self._roles.get(target_id)
        if target is None or target.archived:
            raise RoleError(f"target role unavailable: {target_id}")
        old = self.active
        if old is None:
            self._validate_target(target)
            self._hooks.load(RoleContext(target, target.role_id))
            wake = self._wake_for(target)
            self._hooks.activate(RoleContext(target, target.role_id), wake)
            self._active_id = target_id
            self._save_registry()
            return SwitchResult(target_id, wake, ())
        if old.config.role_id == target_id:
            return SwitchResult(target_id, self._wake_for(target), ())

        events: list[SwitchProgress] = []
        def emit(step: str, completed: int, message: str) -> None:
            event = SwitchProgress(step, completed, 6, message)
            events.append(event)
            self._progress_callback(event)

        committed = False
        try:
            emit("persist_current", 1, "保存当前角色状态与快照")
            self._hooks.persist(old)
            WakeState(old.workspace).save_snapshot(self._snapshot(old), self._clock())
            emit("cancel_tasks", 2, "取消并保存进行中任务")
            self._hooks.cancel_and_persist_tasks(old)
            emit("release_resources", 3, "释放当前角色资源")
            self._hooks.release_resources(old)
            emit("validate_target", 4, "校验目标工作区与状态")
            self._validate_target(target)
            emit("load_target", 5, "加载目标角色配置与状态")
            new_context = RoleContext(target, target.role_id)
            self._hooks.load(new_context)
            wake = self._wake_for(target)
            emit("activate_target", 6, "执行唤醒注入并激活")
            self._hooks.activate(new_context, wake)
            self._active_id = target_id
            self._save_registry()
            committed = True
            return SwitchResult(target_id, wake, tuple(events))
        except Exception as exc:
            try:
                self._hooks.rollback(old)
                self._hooks.load(old)
                self._active_id = old.config.role_id
                self._save_registry()
            except Exception as rollback_exc:
                self._read_only_error = True
                self._active_id = None
                raise RoleError(f"switch failed ({exc}); rollback failed ({rollback_exc})") from rollback_exc
            return SwitchResult(old.config.role_id, None, tuple(events), error=str(exc))
        finally:
            if not committed and self._active_id not in (None, old.config.role_id):
                self._active_id = old.config.role_id

    def archive(self, role_id: str) -> RoleConfig:
        cfg = self._require_inactive(role_id)
        archived = RoleConfig(**{**asdict(cfg), "archived": True})
        self._roles[role_id] = archived
        self._write_role_config(archived)
        self._save_registry()
        return archived

    def restore(self, role_id: str) -> RoleConfig:
        cfg = self._roles.get(role_id)
        if cfg is None or not cfg.archived:
            raise RoleError("role is not archived")
        if len([r for r in self._roles.values() if not r.archived]) >= MAX_ROLES:
            raise RoleError(f"role limit reached ({MAX_ROLES})")
        restored = RoleConfig(**{**asdict(cfg), "archived": False})
        self._roles[role_id] = restored
        self._write_role_config(restored)
        self._save_registry()
        return restored

    def delete_archived(self, role_id: str, *, confirmations: int) -> None:
        cfg = self._roles.get(role_id)
        if cfg is None or not cfg.archived:
            raise RoleError("only archived roles may be permanently deleted")
        if confirmations < 2:
            raise RoleError("permanent deletion requires two confirmations")
        if self.active and self.active.config.role_id == role_id:
            raise RoleError("active role cannot be deleted")
        shutil.rmtree(cfg.workspace)
        del self._roles[role_id]
        self._save_registry()

    def export_package(self, role_id: str, destination: Path) -> Path:
        """Export persona/config files only; memory, state and global channel configs are excluded."""
        cfg = self._roles.get(role_id)
        if cfg is None:
            raise RoleError("unknown role")
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "cetheryh-role-package",
            "version": 1,
            "role": {"name": cfg.name, "self_awareness": cfg.self_awareness, "metadata": cfg.metadata},
            "included": list(ROLE_CARD_FILES),
            "excluded": ["memory", "state", "mind_box", "global_channels", "skills"],
        }
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("package.json", json.dumps(payload, ensure_ascii=False, indent=2))
            for rel in ROLE_CARD_FILES:
                path = cfg.workspace / rel
                if path.is_file():
                    archive.write(path, rel)
        return destination

    def import_package(
        self,
        package: Path,
        workspace: Path,
        *,
        conflict: str,
        renamed_to: str | None = None,
    ) -> RoleConfig:
        """Import an isolated role package. Existing names require rename or explicit replacement."""
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            if any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
                raise RoleError("package contains unsafe paths")
            manifest = json.loads(archive.read("package.json"))
            if manifest.get("format") != "cetheryh-role-package" or manifest.get("version") != 1:
                raise RoleError("unsupported role package")
            original_name = manifest["role"]["name"]
            name_exists = any(r.name.casefold() == original_name.casefold() and not r.archived for r in self._roles.values())
            if name_exists and conflict not in {"rename", "replace"}:
                raise RoleError("role name conflict requires rename or replace")
            if conflict == "rename":
                if not renamed_to or any(r.name.casefold() == renamed_to.casefold() and not r.archived for r in self._roles.values()):
                    raise RoleError("a unique renamed_to value is required")
                name = renamed_to
            elif conflict == "replace" and name_exists:
                existing = next(r for r in self._roles.values() if r.name.casefold() == original_name.casefold() and not r.archived)
                if self.active and self.active.config.role_id == existing.role_id:
                    raise RoleError("cannot replace the active role")
                shutil.rmtree(existing.workspace)
                del self._roles[existing.role_id]
                name = original_name
            else:
                name = original_name
            cfg = self.create_role(name, workspace, self_awareness=manifest["role"].get("self_awareness", "resident"), metadata=manifest["role"].get("metadata", {}))
            allowed = set(ROLE_CARD_FILES)
            for info in archive.infolist():
                if info.filename in allowed:
                    target = cfg.workspace / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
            self._save_registry()
            return cfg

    def _require_inactive(self, role_id: str) -> RoleConfig:
        cfg = self._roles.get(role_id)
        if cfg is None:
            raise RoleError("unknown role")
        if self.active and self.active.config.role_id == role_id:
            raise RoleError("active role must be switched away before archive")
        return cfg

    def _validate_target(self, cfg: RoleConfig) -> None:
        if not cfg.workspace.is_dir():
            raise RoleLoadError(f"role workspace missing: {cfg.workspace}")
        try:
            raw = json.loads((cfg.workspace / "role.json").read_text(encoding="utf-8"))
            if raw.get("role_id") != cfg.role_id:
                raise ValueError("role id mismatch")
            state_path = cfg.workspace / "state.json"
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    raise ValueError("state must be a JSON object")
        except Exception as exc:
            raise RoleLoadError(f"invalid role data for {cfg.role_id}: {exc}") from exc

    @staticmethod
    def _snapshot(role: RoleContext) -> dict:
        path = role.workspace / "state.json"
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        mind_path = role.workspace / "mind_box.json"
        mind = json.loads(mind_path.read_text(encoding="utf-8")) if mind_path.exists() else []
        return {"role_id": role.config.role_id, "state": state, "mind_box": mind}

    @staticmethod
    def _wake_for(cfg: RoleConfig) -> WakePayload | None:
        return WakeState(cfg.workspace).pending(datetime.now(timezone.utc))

    def mark_first_turn_consumed(self, role_id: str) -> None:
        """Consume wake injection only after the first user message begins."""
        self.ensure_role_scope(role_id)
        WakeState(self._roles[role_id].workspace).mark_consumed()

    @staticmethod
    def _write_role_config(cfg: RoleConfig) -> None:
        path = cfg.workspace / "role.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({
            "role_id": cfg.role_id,
            "name": cfg.name,
            "created_at": cfg.created_at,
            "archived": cfg.archived,
            "self_awareness": cfg.self_awareness,
            "metadata": cfg.metadata,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _load_registry(self) -> None:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._active_id = raw.get("active_id")
        for item in raw.get("roles", []):
            cfg = RoleConfig(
                role_id=item["role_id"], name=item["name"], workspace=Path(item["workspace"]),
                created_at=item["created_at"], archived=item.get("archived", False),
                self_awareness=item.get("self_awareness", "resident"), metadata=item.get("metadata", {}),
            )
            self._roles[cfg.role_id] = cfg
        if self._active_id not in self._roles:
            self._active_id = None

    def _save_registry(self) -> None:
        data = {
            "active_id": self._active_id,
            "roles": [
                {**asdict(r), "workspace": str(r.workspace)} for r in self._roles.values()
            ],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
