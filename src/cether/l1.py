"""L1 subjective narrative layer: threshold-triggered or manual, with emotion and relation tags.

L1 is written only when explicit triggers fire (4.21): manual mark, relation event,
high emotion intensity, high salience, or short-window repetition. Otherwise only L0.

Candidate pool is isolated from the hot store; rejected drafts never enter L0/L1 (4.12).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class L1Record:
    """One L1 narrative entry with emotion and relation tags."""
    ts: datetime
    narrative: str
    emotion_tag: str | None
    relation_tag: str | None
    source_l0_ids: list[str]


@dataclass(frozen=True)
class Candidate:
    """One candidate in the pool, waiting for finalization or rejection."""
    ts: datetime
    narrative: str
    emotion_tag: str | None
    relation_tag: str | None
    source_l0_ids: list[str]
    expires_at: datetime


class CandidatePool:
    """Isolated candidate pool with capacity and expiry (4.12). Rejected drafts never enter L0/L1."""
    def __init__(self, path: Path, capacity: int, ttl_seconds: float) -> None:
        self._path = path
        self._capacity = capacity
        self._ttl = ttl_seconds
        path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[Candidate]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            Candidate(
                ts=datetime.fromisoformat(c["ts"]),
                narrative=c["narrative"],
                emotion_tag=c.get("emotion_tag"),
                relation_tag=c.get("relation_tag"),
                source_l0_ids=c["source_l0_ids"],
                expires_at=datetime.fromisoformat(c["expires_at"]),
            )
            for c in raw
        ]

    def _save(self, candidates: list[Candidate]) -> None:
        raw = [
            {
                "ts": c.ts.isoformat(),
                "narrative": c.narrative,
                "emotion_tag": c.emotion_tag,
                "relation_tag": c.relation_tag,
                "source_l0_ids": c.source_l0_ids,
                "expires_at": c.expires_at.isoformat(),
            }
            for c in candidates
        ]
        self._path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, narrative: str, emotion_tag: str | None, relation_tag: str | None,
            source_l0_ids: list[str], now: datetime) -> bool:
        """Add a candidate. Return False if pool is full."""
        candidates = [c for c in self._load() if c.expires_at > now]
        if len(candidates) >= self._capacity:
            return False
        candidates.append(Candidate(
            ts=now,
            narrative=narrative,
            emotion_tag=emotion_tag,
            relation_tag=relation_tag,
            source_l0_ids=source_l0_ids,
            expires_at=now.replace(tzinfo=timezone.utc) + timedelta(seconds=self._ttl),
        ))
        self._save(candidates)
        return True

    def list_pending(self, now: datetime) -> list[Candidate]:
        """Return all non-expired candidates."""
        return [c for c in self._load() if c.expires_at > now]

    def remove(self, narrative: str, now: datetime) -> None:
        """Remove a candidate by narrative match. Used after finalization or rejection."""
        candidates = [c for c in self._load() if c.expires_at > now and c.narrative != narrative]
        self._save(candidates)


class L1Archive:
    """Append-only L1 narrative log."""
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: L1Record) -> None:
        line = {
            "ts": record.ts.isoformat(),
            "narrative": record.narrative,
            "emotion_tag": record.emotion_tag,
            "relation_tag": record.relation_tag,
            "source_l0_ids": record.source_l0_ids,
        }
        with self._path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    def read_all(self) -> list[L1Record]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().split("\n")
        return [
            L1Record(
                ts=datetime.fromisoformat(d["ts"]),
                narrative=d["narrative"],
                emotion_tag=d.get("emotion_tag"),
                relation_tag=d.get("relation_tag"),
                source_l0_ids=d["source_l0_ids"],
            )
            for line in lines if line
            for d in [json.loads(line)]
        ]
