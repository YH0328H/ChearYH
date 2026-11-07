"""L0 objective archive: append-only, zero model calls, keeps raw text and source.

Records are JSON lines. The class exposes no update or delete operation, so
L0 cannot be rewritten through this API.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path


class L0Archive:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, text: str, source: str, weight: str = "normal", *, metadata: dict | None = None) -> str:
        """Append one raw record; optional tier metadata preserves append-only raw facts."""
        if weight not in ("normal", "low"):
            raise ValueError(f"unknown weight {weight!r}")
        record = {
            "id": uuid.uuid4().hex,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "weight": weight,
            "text": text,
        }
        if metadata:
            record["tier_metadata"] = dict(metadata)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return record["id"]

    def __iter__(self) -> Iterator[dict]:
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
