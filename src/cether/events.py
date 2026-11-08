"""Append-only role-local runtime events with cursor-based live subscriptions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RuntimeEvents:
    def __init__(self, world_log: Path) -> None:
        self._world_log = world_log
        self._paused = False
        world_log.parent.mkdir(parents=True, exist_ok=True)

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def record(self, kind: str, description: str, *, metadata: dict | None = None) -> bool:
        """Append one tagged event with optional structured metadata."""
        if self._paused:
            return False
        record = {"ts": datetime.now(timezone.utc).isoformat(), "tags": ["self_world"],
                  "kind": kind, "description": description}
        if metadata:
            record["metadata"] = metadata
        with self._world_log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
        return True

    def subscribe(self, cursor: int = 0, limit: int = 100) -> dict:
        """Read newly appended events after a monotonically increasing line cursor."""
        if cursor < 0 or not 1 <= limit <= 500:
            raise ValueError("cursor must be nonnegative and limit must be between 1 and 500")
        rows = []
        if self._world_log.exists():
            with self._world_log.open("r", encoding="utf-8") as stream:
                for index, line in enumerate(stream, start=1):
                    if index > cursor and line.strip():
                        rows.append((index, json.loads(line)))
                        if len(rows) >= limit:
                            break
        return {"events": [row for _, row in rows], "cursor": rows[-1][0] if rows else cursor,
                "paused": self._paused}
