"""Role card global-exclusive state machine: up to five roles, one active at a time.

Non-active roles are hibernated: state frozen on disk, no perception, no proactive
expression, no background evolution (9.4). Switching saves the current role's state
and pre-close memory snapshot, cancels in-flight tasks, releases resources, switches
workspace paths, loads the target role, and performs one-time wake injection (9.5, patch 2.5).

Any step that fails triggers rollback to the original role (9.11). Scope validation
failures also trigger rollback and never fall back to unscoped mode (patch 7.10).

v1 constraint: all roles pause evolution when the host process is not running (9.10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class RoleStatus(Enum):
    """Current operational status of one role."""
    ACTIVE = "active"
    HIBERNATED = "hibernated"
    ERROR = "error"


@dataclass(frozen=True)
class RoleCard:
    """Immutable reference to one role's configuration and workspace paths.
    
    Each role has an independent memory store directory, independent state,
    independent persona config, independent window & checkpoint, and independent
    appearance mapping; the skill zone is global and shared (9.3).
    """
    role_id: str
    name: str
    workspace_dir: Path
    persona_path: Path
    hard_boundary_path: Path
    appearance_mapping_path: Path


class SwitchStep(Enum):
    """Atomic steps in the role-switch flow, for progress feedback (patch 9.12)."""
    PERSIST_CURRENT = "persist_current"
    CANCEL_TASKS = "cancel_tasks"
    RELEASE_RESOURCES = "release_resources"
    SWITCH_WORKSPACE = "switch_workspace"
    LOAD_TARGET = "load_target"
    WAKE_INJECT = "wake_inject"
    ACTIVATE = "activate"


class RoleRegistry:
    """Global-exclusive role registry: at most five roles, one active, others hibernated.
    
    Switching is atomic with rollback on failure (9.11). The active role owns the
    perception loop, proactive expression, and background evolution; non-active
    roles' state is frozen on disk (9.4).
    
    Scope validation is mandatory; a scope failure aborts the switch and rolls back
    to the original role without falling back to unscoped mode (patch 7.10, 9.11).
    """

    def __init__(self, registry_path: Path, max_roles: int = 5) -> None:
        """Load or initialize the role registry.
        
        Args:
            registry_path: Path to the registry JSON (roles.json)
            max_roles: Maximum number of roles (default 5, per 9.1)
        """
        self._path = registry_path
        self._max_roles = max_roles
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._roles: dict[str, RoleCard] = {}
        self._active_role_id: str | None = None
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._active_role_id = raw.get("active_role_id")
        for r in raw.get("roles", []):
            card = RoleCard(
                role_id=r["role_id"],
                name=r["name"],
                workspace_dir=Path(r["workspace_dir"]),
                persona_path=Path(r["persona_path"]),
                hard_boundary_path=Path(r["hard_boundary_path"]),
                appearance_mapping_path=Path(r["appearance_mapping_path"]),
            )
            self._roles[card.role_id] = card

    def _save(self) -> None:
        raw = {
            "active_role_id": self._active_role_id,
            "roles": [
                {
                    "role_id": card.role_id,
                    "name": card.name,
                    "workspace_dir": str(card.workspace_dir),
                    "persona_path": str(card.persona_path),
                    "hard_boundary_path": str(card.hard_boundary_path),
                    "appearance_mapping_path": str(card.appearance_mapping_path),
                }
                for card in self._roles.values()
            ],
        }
        self._path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_role(self, card: RoleCard) -> bool:
        """Add a new role. Return False if the registry is full or the role_id exists."""
        if len(self._roles) >= self._max_roles:
            return False
        if card.role_id in self._roles:
            return False
        self._roles[card.role_id] = card
        self._save()
        return True

    def remove_role(self, role_id: str) -> bool:
        """Remove a hibernated role. Return False if not found or if active."""
        if role_id not in self._roles:
            return False
        if role_id == self._active_role_id:
            return False
        del self._roles[role_id]
        self._save()
        return True

    def get_role(self, role_id: str) -> RoleCard | None:
        """Return the role card by id, or None if not found."""
        return self._roles.get(role_id)

    def list_roles(self) -> list[RoleCard]:
        """Return all registered roles."""
        return list(self._roles.values())

    def active_role(self) -> RoleCard | None:
        """Return the currently active role, or None if no role is active."""
        if self._active_role_id is None:
            return None
        return self._roles.get(self._active_role_id)

    def role_status(self, role_id: str) -> RoleStatus:
        """Return the operational status of one role."""
        if role_id not in self._roles:
            return RoleStatus.ERROR
        if role_id == self._active_role_id:
            return RoleStatus.ACTIVE
        return RoleStatus.HIBERNATED

    def switch_role(
        self,
        target_role_id: str,
        persist_fn: callable,
        cancel_tasks_fn: callable,
        release_fn: callable,
        load_fn: callable,
        wake_fn: callable,
        validate_scope_fn: callable,
        now: datetime,
    ) -> tuple[bool, str | None]:
        """Switch from the active role to the target role.
        
        Flow (9.5, patch 9.11):
        1. Persist current role state & pre-close memory snapshot
        2. Cancel and persist in-flight tasks (candidate pool persists with state)
        3. Release frontend and background resources
        4. Switch workspace path
        5. Load target role config & state
        6. Validate scope (fail → rollback, never fall back to unscoped)
        7. Perform one-time wake injection
        8. Activate target role
        
        Any step failure triggers rollback to the original role (9.11).
        
        Args:
            target_role_id: ID of the role to switch to
            persist_fn: callable() -> None, persist current role
            cancel_tasks_fn: callable() -> None, cancel in-flight tasks
            release_fn: callable() -> None, release resources
            load_fn: callable(RoleCard) -> None, load target role
            wake_fn: callable(RoleCard, datetime) -> None, inject wake payload
            validate_scope_fn: callable(RoleCard) -> bool, scope validation (True=pass)
            now: Current timestamp for wake injection
        
        Returns:
            (success: bool, error_message: str | None)
        """
        if target_role_id not in self._roles:
            return (False, f"role {target_role_id} not found")
        
        if target_role_id == self._active_role_id:
            return (True, None)  # already active
        
        original_role_id = self._active_role_id
        target_card = self._roles[target_role_id]
        
        try:
            # Step 1: persist current
            if original_role_id is not None:
                persist_fn()
            
            # Step 2: cancel tasks
            cancel_tasks_fn()
            
            # Step 3: release resources
            release_fn()
            
            # Step 4: switch workspace (implicit in load_fn workspace awareness)
            
            # Step 5: load target
            load_fn(target_card)
            
            # Step 6: validate scope (hard fail, never fall back)
            if not validate_scope_fn(target_card):
                raise ValueError(f"scope validation failed for role {target_role_id}")
            
            # Step 7: wake injection
            wake_fn(target_card, now)
            
            # Step 8: activate
            self._active_role_id = target_role_id
            self._save()
            return (True, None)
        
        except Exception as exc:
            # Rollback to original role (9.11)
            if original_role_id is not None:
                try:
                    original_card = self._roles[original_role_id]
                    load_fn(original_card)
                    self._active_role_id = original_role_id
                    self._save()
                except Exception:
                    # Rollback itself failed → enter read-only error state (9.11)
                    self._active_role_id = None
                    self._save()
                    return (False, f"switch failed and rollback also failed: {exc}")
            return (False, f"switch failed: {exc}")
