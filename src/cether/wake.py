"""Pre-close memory snapshot and one-time wake injection.

The snapshot is written atomically (temp file, then os.replace), so a crash
never leaves a half-written file. The injection is built from the last good
snapshot and the time since close. It is marked consumed only after the user
starts a dialogue, so a switch-away before any reply leaves it pending (patch 2.5).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class WakePayload:
    gap_seconds: float
    snapshot: dict


class WakeState:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = directory / "wake.json"

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)

    def save_snapshot(self, snapshot: dict, closed_at: datetime) -> None:
        """Persist a snapshot taken at close. A new close makes any earlier injection pending again."""
        self._write({
            "closed_at": closed_at.isoformat(),
            "snapshot": snapshot,
            "consumed": False,
        })

    def pending(self, now: datetime) -> WakePayload | None:
        """Return the wake payload if one is due, else None."""
        data = self._read()
        if not data or data.get("consumed"):
            return None
        closed_at = datetime.fromisoformat(data["closed_at"])
        return WakePayload(gap_seconds=(now - closed_at).total_seconds(), snapshot=data["snapshot"])

    def mark_consumed(self) -> None:
        """Call on the first user turn after wake. Only then is the injection spent."""
        data = self._read()
        if data and not data.get("consumed"):
            data["consumed"] = True
            self._write(data)
