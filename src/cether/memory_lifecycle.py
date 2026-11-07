"""Role-local memory lifecycle controls that preserve append-only L0 facts.

The lifecycle index is a reversible overlay: deleting, cooling, or weighting a
record changes retrieval visibility and presentation metadata, never the raw
L0 JSONL. This keeps objective evidence immutable while giving the user
explicit control over hot/cold memory behavior.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .l0 import L0Archive
from .roles import RoleContext, RoleRegistry


@dataclass(frozen=True)
class MemoryLifecycleResult:
    memory_id: str
    operation: str
    status: str
    storage_unchanged: bool = True
    injected: bool = False


class MemoryLifecycleService:
    """Apply role-scoped forget/restore operations through a sidecar index."""

    def __init__(self, role: RoleContext, registry: RoleRegistry) -> None:
        self.role = role
        self.registry = registry
        self.archive = L0Archive(role.workspace / "memory" / "l0.jsonl")
        self._path = role.workspace / "memory" / "lifecycle.json"
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._entries: dict[str, dict[str, Any]] = {}
            self._injected: list[str] = []
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._entries = dict(raw.get("entries", {}))
        self._injected = [str(item) for item in raw.get("injected", [])]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": self._entries, "injected": self._injected}
        temp = self._path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self._path)

    def _record(self, memory_id: str) -> dict[str, Any]:
        self.registry.ensure_role_scope(self.role.scope_id)
        for record in self.archive:
            if str(record.get("id")) == memory_id:
                return record
        raise KeyError(f"unknown memory: {memory_id}")

    def forget(self, memory_id: str, choice: str) -> MemoryLifecycleResult:
        """Delete, slowly cool, or immediately move one record out of retrieval."""
        self._record(memory_id)
        if choice not in {"delete", "decrease_weight", "move_to_cold"}:
            raise ValueError("unknown forget choice")
        entry = self._entries.setdefault(memory_id, {})
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        if choice == "delete":
            entry.update({"status": "deleted", "weight_factor": 0.0})
        elif choice == "decrease_weight":
            entry.update({"status": "cooling", "weight_factor": 0.5})
        else:
            entry.update({"status": "cold", "weight_factor": 0.0})
        self._save()
        return MemoryLifecycleResult(memory_id, choice, entry["status"])

    def restore(self, memory_id: str, choice: str) -> MemoryLifecycleResult:
        """Boost, move hot, or inject a cold record once into the next turn."""
        self._record(memory_id)
        if choice not in {"boost", "move_to_hot", "inject_once"}:
            raise ValueError("unknown restore choice")
        entry = self._entries.setdefault(memory_id, {})
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        if choice == "boost":
            entry.update({"status": "hot", "weight_factor": 1.5})
        elif choice == "move_to_hot":
            entry.update({"status": "hot", "weight_factor": 1.0})
        else:
            if memory_id not in self._injected:
                self._injected.append(memory_id)
            entry.update({"status": "cold", "weight_factor": 0.0})
        self._save()
        return MemoryLifecycleResult(memory_id, choice, entry.get("status", "cold"), injected=choice == "inject_once")

    def excluded_ids(self) -> frozenset[str]:
        """Return IDs excluded from proactive retrieval (deleted, cold, cooling)."""
        self.registry.ensure_role_scope(self.role.scope_id)
        return frozenset(
            memory_id for memory_id, entry in self._entries.items()
            if entry.get("status") in {"deleted", "cold", "cooling"}
        )

    def consume_injections(self) -> tuple[dict[str, Any], ...]:
        """Return and clear one-shot records for the next conversation context."""
        self.registry.ensure_role_scope(self.role.scope_id)
        ids = tuple(self._injected)
        rows = {str(row.get("id")): row for row in self.archive}
        self._injected.clear()
        self._save()
        return tuple(rows[memory_id] for memory_id in ids if memory_id in rows)

    def annotate(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return a UI/retrieval view with lifecycle state, preserving the input."""
        item = dict(record)
        entry = self._entries.get(str(record.get("id")), {})
        item["lifecycle_status"] = entry.get("status", "hot")
        item["lifecycle_weight_factor"] = float(entry.get("weight_factor", 1.0))
        return item

    def visible_records(self) -> list[dict[str, Any]]:
        excluded = self.excluded_ids()
        return [self.annotate(row) for row in self.archive if str(row.get("id")) not in excluded]
