"""Tests for src/cether/spatial_index.py: fixed rooms, capacity, overflow,
grow-only slots, and fixed-route patrol (TASK.md 39)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cether.spatial_index import SpatialIndex, SpatialIndexConfig


def make_index(room_capacity: int = 3) -> SpatialIndex:
    return SpatialIndex(SpatialIndexConfig(room_capacity=room_capacity))


class PlacementTests(unittest.TestCase):
    def test_first_placement_goes_to_room_zero(self) -> None:
        idx = make_index()
        room, slot_id = idx.place("mem-1")
        self.assertEqual((room, slot_id), (0, 0))

    def test_sequential_placements_fill_room_in_order(self) -> None:
        idx = make_index(room_capacity=3)
        coords = [idx.place(f"mem-{i}") for i in range(3)]
        self.assertEqual(coords, [(0, 0), (0, 1), (0, 2)])

    def test_placing_same_memory_twice_returns_same_slot(self) -> None:
        idx = make_index()
        first = idx.place("mem-1")
        second = idx.place("mem-1")
        self.assertEqual(first, second)
        self.assertEqual(idx.occupied_count(), 1)


class OverflowTests(unittest.TestCase):
    def test_full_room_opens_new_room(self) -> None:
        idx = make_index(room_capacity=2)
        idx.place("mem-1")
        idx.place("mem-2")
        room, slot_id = idx.place("mem-3")
        self.assertEqual((room, slot_id), (1, 0))
        self.assertEqual(idx.room_count, 2)

    def test_many_rooms_open_as_needed(self) -> None:
        idx = make_index(room_capacity=2)
        coords = [idx.place(f"mem-{i}") for i in range(5)]
        self.assertEqual(
            coords,
            [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)],
        )
        self.assertEqual(idx.room_count, 3)


class SlotGrowOnlyTests(unittest.TestCase):
    def test_removed_slot_id_is_never_reused(self) -> None:
        idx = make_index(room_capacity=2)
        idx.place("mem-1")
        idx.place("mem-2")
        idx.remove("mem-1")
        # Room 0 is full of slot ids 0,1 even though slot 0 is vacated;
        # the next placement must open room 1, not reuse room-0 slot 0.
        room, slot_id = idx.place("mem-3")
        self.assertEqual((room, slot_id), (1, 0))

    def test_vacated_slot_remains_in_patrol_route_as_unoccupied(self) -> None:
        idx = make_index(room_capacity=3)
        idx.place("mem-1")
        idx.place("mem-2")
        idx.remove("mem-1")
        route = idx.patrol_route()
        self.assertEqual(len(route), 2)
        self.assertFalse(route[0].occupied)
        self.assertIsNone(route[0].memory_id)
        self.assertTrue(route[1].occupied)
        self.assertEqual(route[1].memory_id, "mem-2")

    def test_remove_unknown_memory_returns_false(self) -> None:
        idx = make_index()
        self.assertFalse(idx.remove("ghost"))

    def test_locate_after_removal_returns_none(self) -> None:
        idx = make_index()
        idx.place("mem-1")
        idx.remove("mem-1")
        self.assertIsNone(idx.locate("mem-1"))


class PatrolRouteTests(unittest.TestCase):
    def test_route_is_room_ascending_then_slot_ascending(self) -> None:
        idx = make_index(room_capacity=2)
        for i in range(5):
            idx.place(f"mem-{i}")
        route = idx.patrol_route()
        coords = [(s.room, s.slot_id) for s in route]
        self.assertEqual(
            coords,
            [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)],
        )

    def test_route_is_deterministic_across_calls(self) -> None:
        idx = make_index(room_capacity=2)
        for i in range(4):
            idx.place(f"mem-{i}")
        first = idx.patrol_route()
        second = idx.patrol_route()
        self.assertEqual(
            [(s.room, s.slot_id, s.memory_id) for s in first],
            [(s.room, s.slot_id, s.memory_id) for s in second],
        )

    def test_empty_index_has_empty_route(self) -> None:
        idx = make_index()
        self.assertEqual(idx.patrol_route(), [])


class OccupiedCountTests(unittest.TestCase):
    def test_count_reflects_placements_and_removals(self) -> None:
        idx = make_index(room_capacity=3)
        idx.place("mem-1")
        idx.place("mem-2")
        self.assertEqual(idx.occupied_count(), 2)
        idx.remove("mem-1")
        self.assertEqual(idx.occupied_count(), 1)

    def test_empty_index_has_zero_occupied(self) -> None:
        idx = make_index()
        self.assertEqual(idx.occupied_count(), 0)


if __name__ == "__main__":
    unittest.main()
