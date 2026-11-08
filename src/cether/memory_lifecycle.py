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


class ColdMemoryArchive:
    """Role-local monthly JSONL shards with an atomic ID-to-shard index.

    Cold records remain outside L0 retrieval. The immutable L0 source is kept
    as provenance; lifecycle visibility determines which copy is active.
    """

    def __init__(self, root: Path, *, scope_id: str) -> None:
        if not scope_id:
            raise ValueError("cold archive scope_id must be non-empty")
        self.root = root
        self.scope_id = scope_id
        self._index_path = root / "index.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict[str, str]:
        if not self._index_path.exists():
            return {}
        payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("cold archive index is corrupt")
        if payload.get("scope_id") != self.scope_id:
            raise ValueError("cold archive scope mismatch")
        index = payload.get("records", {})
        if not isinstance(index, dict):
            raise ValueError("cold archive index is corrupt")
        records: dict[str, str] = {}
        for memory_id, shard_value in index.items():
            shard = str(shard_value)
            if Path(shard).name != shard or len(shard) != 12 or not shard.endswith(".jsonl"):
                raise ValueError("cold archive index contains an invalid shard path")
            try:
                datetime.strptime(shard[:7], "%Y-%m")
            except ValueError as exc:
                raise ValueError("cold archive index contains an invalid shard name") from exc
            records[str(memory_id)] = shard
        return records

    def _save_index(self, records: dict[str, str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"scope_id": self.scope_id, "records": records}
        temp = self._index_path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self._index_path)

    def archive(self, record: dict[str, Any]) -> str:
        """Idempotently place one raw L0 record in its UTC-month shard."""
        memory_id = str(record.get("id", ""))
        if not memory_id:
            raise ValueError("cold archive record requires an id")
        ts = datetime.fromisoformat(str(record["ts"]))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        shard_name = f"{ts.astimezone(timezone.utc):%Y-%m}.jsonl"
        index = self._load_index()
        previous = index.get(memory_id)
        if previous is not None:
            if previous != shard_name:
                raise ValueError("cold archive ID already maps to a different shard")
            return previous
        shard_path = self.root / shard_name
        if shard_path.exists():
            for line in shard_path.read_text(encoding="utf-8").splitlines():
                if line.strip() and str(json.loads(line).get("id")) == memory_id:
                    index[memory_id] = shard_name
                    self._save_index(index)
                    return shard_name
        with shard_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        index[memory_id] = shard_name
        self._save_index(index)
        return shard_name

    def restore(self, memory_id: str) -> dict[str, Any]:
        """Read a cold record by indexed ID without touching the hot archive."""
        index = self._load_index()
        shard = index.get(memory_id)
        if shard is None:
            raise KeyError(f"unknown cold memory: {memory_id}")
        path = self.root / shard
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if str(record.get("id")) == memory_id:
                    return record
        raise ValueError(f"cold archive index points to missing record: {memory_id}")

    def page(self, *, cursor: str | None = None, limit: int = 100) -> tuple[list[dict[str, Any]], str | None, int]:
        """Return reverse-chronological cold records using an opaque offset cursor."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        index = self._load_index()
        ids_by_shard: dict[str, set[str]] = {}
        for memory_id, shard in index.items():
            ids_by_shard.setdefault(shard, set()).add(memory_id)
        rows: list[dict[str, Any]] = []
        for shard, memory_ids in ids_by_shard.items():
            shard_path = self.root / shard
            found: set[str] = set()
            for line in shard_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                memory_id = str(record.get("id", ""))
                if memory_id in memory_ids:
                    rows.append(record)
                    found.add(memory_id)
            missing = memory_ids - found
            if missing:
                raise ValueError(f"cold archive index points to missing records: {', '.join(sorted(missing))}")
        rows.sort(key=lambda row: (str(row.get("ts", "")), str(row.get("id", ""))), reverse=True)
        try:
            offset = max(0, int(cursor)) if cursor is not None else 0
        except ValueError as exc:
            raise ValueError("invalid cold archive cursor") from exc
        page = rows[offset:offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(rows) else None
        return page, next_cursor, len(rows)


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
        self.cold_archive = ColdMemoryArchive(role.workspace / "memory" / "cold", scope_id=role.scope_id)
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
        record = self._record(memory_id)
        if choice not in {"delete", "decrease_weight", "move_to_cold"}:
            raise ValueError("unknown forget choice")
        entry = self._entries.setdefault(memory_id, {})
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        if choice == "delete":
            entry.update({"status": "deleted", "weight_factor": 0.0})
        elif choice == "decrease_weight":
            entry.update({"status": "cooling", "weight_factor": 0.5})
        else:
            shard = self.cold_archive.archive(record)
            entry.update({"status": "cold", "weight_factor": 0.0, "cold_shard": shard})
        self._save()
        return MemoryLifecycleResult(memory_id, choice, entry["status"])

    def deepen(self, memory_id: str, amount: float = 0.1) -> float:
        """Persist a bounded user weight boost without mutating the L0 record."""
        self.registry.ensure_role_scope(self.role.scope_id)
        record = self._record(memory_id)
        if not 0 < amount <= 1:
            raise ValueError("deepen amount must be between 0 and 1")
        entry = self._entries.setdefault(memory_id, {})
        factor = min(2.0, max(1.0, float(entry.get("weight_factor", 1.0))) + amount)
        entry.update({"status": "hot", "weight_factor": factor,
                      "updated_at": datetime.now(timezone.utc).isoformat()})
        self._save()
        base = float((record.get("tier_metadata") or {}).get("weight", 0.5))
        return min(1.0, base * factor)

    def restore(self, memory_id: str, choice: str) -> MemoryLifecycleResult:
        """Boost, move hot, or inject a cold record once into the next turn."""
        self.registry.ensure_role_scope(self.role.scope_id)
        self._record(memory_id)
        if choice not in {"boost", "move_to_hot", "inject_once"}:
            raise ValueError("unknown restore choice")
        entry = self._entries.setdefault(memory_id, {})
        if entry.get("status") == "cold":
            self.cold_archive.restore(memory_id)
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
        """Read one-shot records; successful conversation commit removes them."""
        self.registry.ensure_role_scope(self.role.scope_id)
        ids = tuple(self._injected)
        rows = {str(row.get("id")): row for row in self.archive}
        return tuple(rows[memory_id] for memory_id in ids if memory_id in rows)

    def commit_injections(self, records: tuple[dict[str, Any], ...]) -> None:
        """Commit one-shot delivery only after the conversation was persisted."""
        self.registry.ensure_role_scope(self.role.scope_id)
        delivered = {str(row.get("id")) for row in records}
        self._injected = [memory_id for memory_id in self._injected if memory_id not in delivered]
        self._save()

    def cold_page(self, *, cursor: str | None = None, limit: int = 100) -> tuple[list[dict[str, Any]], str | None, int]:
        """List indexed cold records with lifecycle annotations under this role scope."""
        self.registry.ensure_role_scope(self.role.scope_id)
        rows, next_cursor, total = self.cold_archive.page(cursor=cursor, limit=limit)
        return [self.annotate(row) for row in rows], next_cursor, total

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
