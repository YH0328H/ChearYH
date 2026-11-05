"""Spatial index for high-weight memory nodes (4.6): fixed rooms, capacity-bounded,
new room on overflow, slots only grow (never recycled), fixed-route patrol.

High-weight memories (relation events, high-emotion records) are placed into a
spatial index so they can be retrieved via fixed-route traversal instead of pure
search, and so a future "memory starfield" visualization has stable coordinates
to render against (ARCHITECTURE.md parameterization principle: coordinates must
be deterministic and reproducible, not randomly assigned).

Design mapped to TASK.md 39:
- 固定房间 (fixed rooms): each room has a stable id and a fixed capacity.
- 容量限制 (capacity limit): a room stops accepting new slots once full.
- 满员开新房 (new room on overflow): the index opens room N+1 once room N is full.
- 桩位只增不回收 (slots only grow, never recycled): removing a memory frees the
  memory reference but the slot id is never reused, so patrol order and any
  external coordinate cache stay stable across the character's lifetime.
- 固定路线巡游 (fixed-route patrol): traversal order is deterministic — room
  index ascending, then slot index ascending within a room.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpatialIndexConfig:
    """Configuration for room capacity. Room capacity is uniform across rooms
    so patrol order stays predictable; per-room overrides are not needed by
    any current requirement and would add state without a use case."""
    room_capacity: int = 50


@dataclass(frozen=True)
class Slot:
    """One occupied or vacated slot. `occupied=False` means the memory was
    removed, but the slot id is retained (never recycled) per 4.6."""
    room: int
    slot_id: int
    memory_id: str | None
    occupied: bool = True


class SpatialIndex:
    """Fixed-room, grow-only spatial index for high-weight memory placement.

    Internal layout is a list of rooms; each room is a list of Slot entries
    in slot-id order. New slots are only ever appended — a vacated slot is
    marked unoccupied in place and never reused, so slot identity (room,
    slot_id) is a stable coordinate for the lifetime of the character.
    """

    def __init__(self, config: SpatialIndexConfig) -> None:
        self._config = config
        self._rooms: list[list[Slot]] = [[]]
        self._memory_to_slot: dict[str, tuple[int, int]] = {}

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    def place(self, memory_id: str) -> tuple[int, int]:
        """Place a high-weight memory into the index. Returns (room, slot_id).

        Fills the current (last) room until it reaches capacity, then opens
        a new room (4.6 "满员开新房"). Slot ids within a room are assigned by
        ascending position and never reused even after removal (4.6 "桩位只
        增不回收").
        """
        if memory_id in self._memory_to_slot:
            return self._memory_to_slot[memory_id]

        room_index = len(self._rooms) - 1
        room = self._rooms[room_index]
        if len(room) >= self._config.room_capacity:
            room_index += 1
            room = []
            self._rooms.append(room)

        slot_id = len(room)
        room.append(Slot(room=room_index, slot_id=slot_id, memory_id=memory_id))
        self._memory_to_slot[memory_id] = (room_index, slot_id)
        return (room_index, slot_id)

    def remove(self, memory_id: str) -> bool:
        """Vacate the slot holding `memory_id`. The slot id is kept (marked
        unoccupied) rather than deleted, so no later placement can reuse it
        and patrol order stays stable. Returns False if not found."""
        coords = self._memory_to_slot.get(memory_id)
        if coords is None:
            return False
        room_index, slot_id = coords
        slot = self._rooms[room_index][slot_id]
        self._rooms[room_index][slot_id] = Slot(
            room=room_index, slot_id=slot_id, memory_id=None, occupied=False
        )
        del self._memory_to_slot[memory_id]
        return True

    def locate(self, memory_id: str) -> tuple[int, int] | None:
        """Return (room, slot_id) for an occupied memory, or None."""
        return self._memory_to_slot.get(memory_id)

    def patrol_route(self) -> list[Slot]:
        """Fixed-route traversal (4.6 "固定路线巡游"): room index ascending,
        then slot index ascending within each room. Includes vacated slots
        so the route shape itself stays stable even as memories come and go
        — callers that only care about live memories should filter on
        `occupied`."""
        route: list[Slot] = []
        for room in self._rooms:
            route.extend(room)
        return route

    def occupied_count(self) -> int:
        return len(self._memory_to_slot)
