"""Screen perception: hash change detection, zero model calls when nothing changed.

The capture function returns a small grayscale thumbnail. Only its average
hash is kept, plus a short scene description when the screen changed. The
raw capture is dropped after each tick and never written to disk.

Events go to an append-only world log tagged `self_world`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

Thumbnail = list[int]  # grayscale values 0-255, length = hash_size * hash_size


def average_hash(pixels: Thumbnail) -> int:
    """64-bit average hash: bit i is 1 if pixel i is brighter than the mean."""
    mean = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | (1 if value > mean else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


@dataclass(frozen=True)
class Tick:
    changed: bool
    description: str | None
    distance: int | None


class Perceiver:
    def __init__(
        self,
        capture: Callable[[], Thumbnail],
        describe: Callable[[], str],
        world_log: Path,
        hamming_threshold: int = 5,
    ) -> None:
        self._capture = capture
        self._describe = describe
        self._world_log = world_log
        self._threshold = hamming_threshold
        self._last_hash: int | None = None
        self._active = True
        self.model_calls = 0
        world_log.parent.mkdir(parents=True, exist_ok=True)

    def pause(self) -> None:
        self._active = False

    def resume(self) -> None:
        self._active = True

    def tick(self) -> Tick:
        if not self._active:
            return Tick(False, None, None)
        thumb = self._capture()
        current = average_hash(thumb)
        del thumb  # raw pixels are not kept past this point

        if self._last_hash is None:
            distance = None
            changed = True
        else:
            distance = hamming(current, self._last_hash)
            changed = distance > self._threshold

        self._last_hash = current
        if not changed:
            return Tick(False, None, distance)

        self.model_calls += 1
        description = self._describe()
        self._append_world(description)
        return Tick(True, description, distance)

    def _append_world(self, description: str) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tags": ["self_world"],
            "kind": "screen_change",
            "description": description,
        }
        with self._world_log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
