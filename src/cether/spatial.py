"""Spatial index: fixed rooms, capacity-bounded, fixed-route patrol (TASK.md 39).

Design constraints (TASK.md 一.39, 四.6, verbatim):
- 固定房间 (fixed rooms): rooms are pre-declared containers, not dynamically shaped.
- 容量限制 (capacity limit): each room holds at most `capacity` slots.
- 满员开新房 (open new room when full): once a room is full, new slots go to the
  next room; a new room is opened on demand, never by splitting/resizing an old one.
- 桩位只增不回收 (slots only grow, never reclaimed): once a slot is assigned to a
  memory id, it is never freed/reused even if the memory later decays or is deleted.
  This matches the project's "memory star map" visualization need: a memory's
  spatial position must stay stable for its lifetime.
- 固定路线巡游 (fixed-route patrol): visiting order is deterministic room-then-slot
  ascending order, not random; used by sleep-phase index tidying (TASK.md 264) and
  by idle "wander" behaviors (idle.py) that want a stable, explainable walk order.

High-weight memories are routed here per TASK.md 4.4 ("高权重走固定空间索引");
this module only indexes slot *positions*, it does not decide which memories
qualify as high-weight (that is the caller's job, e.g. via multipliers/weight tier).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SlotRef:
    """A fixed, never-reclaimed position: (room index, slot index within room)."""
    room: int
    slot: int


@dataclass(frozen=True)
class SpatialIndexConfig:
    """Room capacity. Rooms are homogeneous: every room has the same capacity."""
    room_capacity: int = 64


class SpatialIndex:
    """Append-only room/slot assignment for memory ids.

    Internal invariant: `_assignments` (memory_id -> SlotRef) and `_by_slot`
    (SlotRef -> memory_id) only ever grow. `remove()` does NOT free the slot
    for reuse; it only removes the memory_id -> content association so the
    id can no longer be looked up, while the slot remains permanently
    occupied (reported by `occupied_slots`) per the "桩位只增不回收" rule.
    """

    def __init__(self, config: SpatialIndexConfig | None = None) -> None:
        self.config = config or SpatialIndexConfig()
        self._assignments: dict[str, SlotRef] = {}
        self._occupied: set[SlotRef] = set()
        self._next_room = 0
        self._next_slot = 0

    def _advance_cursor(self) -> None:
        self._next_slot += 1
        if self._next_slot >= self.config.room_capacity:
            self._next_slot = 0
            self._next_room += 1

    def assign(self, memory_id: str) -> SlotRef:
        """Assign a fixed slot to memory_id. Idempotent: re-assigning the same
        id returns its existing slot rather than consuming a new one."""
        if memory_id in self._assignments:
            return self._assignments[memory_id]
        ref = SlotRef(room=self._next_room, slot=self._next_slot)
        self._assignments[memory_id] = ref
        self._occupied.add(ref)
        self._advance_cursor()
        return ref

    def remove(self, memory_id: str) -> None:
        """Drop the lookup for memory_id. The slot stays permanently occupied
        (never reclaimed) so later ids keep opening new rooms instead of
        back-filling, matching TASK.md 39 "桩位只增不回收"."""
        self._assignments.pop(memory_id, None)

    def slot_of(self, memory_id: str) -> SlotRef | None:
        return self._assignments.get(memory_id)

    def room_count(self) -> int:
        """Number of rooms opened so far (at least 1 once anything is assigned)."""
        if not self._occupied:
            return 0
        return max(ref.room for ref in self._occupied) + 1

    def is_room_full(self, room: int) -> bool:
        occupied_in_room = sum(1 for ref in self._occupied if ref.room == room)
        return occupied_in_room >= self.config.room_capacity

    def occupied_slots(self) -> list[SlotRef]:
        """All slots ever occupied, including ones whose memory_id was removed."""
        return sorted(self._occupied, key=lambda r: (r.room, r.slot))

    def patrol_route(self) -> list[tuple[SlotRef, str | None]]:
        """Fixed-route patrol order (TASK.md 39, 264): ascending (room, slot).
        Deterministic — same occupied set always yields the same order, which
        is required for sleep-phase tidying and idle wander to be reproducible.
        Returns (slot, memory_id) pairs; memory_id is None for removed slots
        (slot still visited, just empty, since slots are never reclaimed).
        """
        reverse_lookup = {ref: mid for mid, ref in self._assignments.items()}
        return [(ref, reverse_lookup.get(ref)) for ref in self.occupied_slots()]

    def save(self, path: Path) -> None:
        payload = {
            "config": {"room_capacity": self.config.room_capacity},
            "assignments": {mid: [ref.room, ref.slot] for mid, ref in self._assignments.items()},
            "occupied": [[ref.room, ref.slot] for ref in self._occupied],
            "next_room": self._next_room,
            "next_slot": self._next_slot,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SpatialIndex":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        idx = cls(SpatialIndexConfig(room_capacity=data["config"]["room_capacity"]))
        idx._assignments = {mid: SlotRef(r, s) for mid, (r, s) in data["assignments"].items()}
        idx._occupied = {SlotRef(r, s) for r, s in data["occupied"]}
        idx._next_room = data["next_room"]
        idx._next_slot = data["next_slot"]
        return idx
