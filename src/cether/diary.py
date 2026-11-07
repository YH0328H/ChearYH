"""Immutable, role-local diary views backed by append-only L1 records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .l1 import L1Archive
from .roles import RoleContext, RoleRegistry


class DiaryService:
    """Read or hide diary entries without modifying their L0 provenance."""

    def __init__(self, role: RoleContext, registry: RoleRegistry) -> None:
        self.role = role
        self.registry = registry
        self.archive = L1Archive(role.workspace / "memory" / "l1.jsonl")
        self._hidden_path = role.workspace / "memory" / "diary-hidden.json"
        self._hidden = self._load_hidden()

    def _load_hidden(self) -> set[str]:
        if not self._hidden_path.exists():
            return set()
        raw = json.loads(self._hidden_path.read_text(encoding="utf-8"))
        return {str(value) for value in raw if isinstance(value, str)}

    def _save_hidden(self) -> None:
        self._hidden_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._hidden_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(sorted(self._hidden), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self._hidden_path)

    def list_entries(self) -> list[dict[str, Any]]:
        """Return newest visible diary entries; entries remain immutable."""
        self.registry.ensure_role_scope(self.role.scope_id)
        rows = []
        for index, record in enumerate(self.archive.read_all()):
            entry = {
                "diary_id": f"{record.ts.isoformat()}:{index}",
                "ts": record.ts.isoformat(),
                "narrative": record.narrative,
                "emotion_tag": record.emotion_tag,
                "relation_tag": record.relation_tag,
                "source_l0_ids": list(record.source_l0_ids),
            }
            if entry["diary_id"] not in self._hidden:
                rows.append(entry)
        rows.reverse()
        return rows

    def delete(self, diary_id: str) -> bool:
        """Hide a diary entry while leaving L1 and source L0 files untouched."""
        self.registry.ensure_role_scope(self.role.scope_id)
        known = {item["diary_id"] for item in self.list_entries()}
        if diary_id not in known and diary_id not in self._hidden:
            raise KeyError(f"unknown diary: {diary_id}")
        self._hidden.add(diary_id)
        self._save_hidden()
        return True
