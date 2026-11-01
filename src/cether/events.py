"""Runtime events (tool failures, tick errors) go to the world log tagged self_world.

They have their own pause, separate from screen capture. Pausing screen
capture does not stop runtime events, and pausing runtime events does not
stop screen capture (spec 3.9.4).
"""

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

    def record(self, kind: str, description: str) -> bool:
        """Append one runtime event. Return False if runtime events are paused."""
        if self._paused:
            return False
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tags": ["self_world"],
            "kind": kind,
            "description": description,
        }
        with self._world_log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
