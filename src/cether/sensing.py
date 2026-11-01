"""Silent learning, first-run notice, and the "what it saw" data view.

Silent learning is a perception-layer mode. It only archives low-weight L0
records. It never calls a model and never speaks. It is separate from the
capture pause and from silent mode (spec 3.8).
"""

from __future__ import annotations

import json
from pathlib import Path

from .l0 import L0Archive


class SilentLearner:
    def __init__(self, archive: L0Archive, enabled: bool = False) -> None:
        self._archive = archive
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def observe(self, text: str, source: str) -> str | None:
        """Archive one low-weight record if enabled. Return its id, or None if off."""
        if not self._enabled:
            return None
        return self._archive.append(text, source, weight="low")


class FirstRunNotice:
    """Tracks whether the one-time perception notice has been shown."""

    def __init__(self, flag: Path) -> None:
        self._flag = flag

    def due(self) -> bool:
        return not self._flag.exists()

    def mark_shown(self) -> None:
        self._flag.parent.mkdir(parents=True, exist_ok=True)
        self._flag.write_text("shown\n", encoding="utf-8")


def list_seen(world_log: Path) -> list[dict]:
    """Return screen-change records from the world log, oldest first."""
    if not world_log.exists():
        return []
    rows: list[dict] = []
    with world_log.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if "self_world" in rec.get("tags", []) and rec.get("kind") == "screen_change":
                rows.append(rec)
    return rows
