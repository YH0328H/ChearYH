"""Tests for spatial index: fixed rooms, capacity, slots-never-reclaimed, fixed-route patrol."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cether.spatial import SlotRef, SpatialIndex, SpatialIndexConfig


def make_index(capacity: int = 4) -> SpatialIndex:
    return SpatialIndex(SpatialIndexConfig(room_capacity=capacity))


class AssignTests(unittest.TestCase):
    def test_first_assignment_is_room_zero_slot_zero(self):
        idx = make_index()
        ref = idx.assign("m1")
        self.assertEqual(ref, SlotRef(room=0, slot=0))

    def test_sequential_assignments_fill_room_in_order(self):
        idx = make_index(capacity=4)
        refs = [idx.assign(f"m{i}") for i in range(4)]
        self.assertEqual(refs, [SlotRef(0, 0), SlotRef(0, 1), SlotRef(0, 2), SlotRef(0, 3)])

    def test_reassigning_same_id_returns_same_slot(self):
        idx = make_index()
        first = idx.assign("m1")
        second = idx.assign("m1")
        self.assertEqual(first, second)
        self.assertEqual(idx.room_count(), 1)


class RoomOverflowTests(unittest.TestCase):
    def test_full_room_opens_new_room_instead_of_resizing(self):
        idx = make_index(capacity=2)
        idx.assign("a")
        idx.assign("b")
        self.assertTrue(idx.is_room_full(0))
        third = idx.assign("c")
        self.assertEqual(third.room, 1)
        self.assertEqual(third.slot, 0)

    def test_room_count_reflects_rooms_opened(self):
        idx = make_index(capacity=2)
        for name in ["a", "b", "c", "d", "e"]:
            idx.assign(name)
        # 5 items, capacity 2 per room -> rooms 0,1 full, room 2 has 1 item
        self.assertEqual(idx.room_count(), 3)

    def test_empty_index_has_zero_rooms(self):
        idx = make_index()
        self.assertEqual(idx.room_count(), 0)


class SlotsNeverReclaimedTests(unittest.TestCase):
    def test_remove_does_not_free_slot_for_reuse(self):
        idx = make_index(capacity=2)
        idx.assign("a")
        idx.assign("b")
        idx.remove("a")
        # room 0 is still full even though "a" was removed
        self.assertTrue(idx.is_room_full(0))
        third = idx.assign("c")
        self.assertEqual(third.room, 1)  # new room opened, not backfilled into room 0

    def test_removed_slot_still_counted_in_occupied_slots(self):
        idx = make_index()
        idx.assign("a")
        idx.remove("a")
        self.assertEqual(len(idx.occupied_slots()), 1)

    def test_slot_of_returns_none_after_removal(self):
        idx = make_index()
        idx.assign("a")
        idx.remove("a")
        self.assertIsNone(idx.slot_of("a"))

    def test_remove_unknown_id_is_a_noop(self):
        idx = make_index()
        idx.remove("never-assigned")  # must not raise
        self.assertEqual(idx.room_count(), 0)


class PatrolRouteTests(unittest.TestCase):
    def test_patrol_route_is_ascending_room_then_slot(self):
        idx = make_index(capacity=2)
        idx.assign("a")
        idx.assign("b")
        idx.assign("c")
        route = idx.patrol_route()
        refs = [ref for ref, _ in route]
        self.assertEqual(refs, [SlotRef(0, 0), SlotRef(0, 1), SlotRef(1, 0)])

    def test_patrol_route_is_deterministic_across_calls(self):
        idx = make_index(capacity=3)
        for name in ["x", "y", "z", "w"]:
            idx.assign(name)
        self.assertEqual(idx.patrol_route(), idx.patrol_route())

    def test_patrol_route_visits_removed_slots_with_none_memory_id(self):
        idx = make_index()
        idx.assign("a")
        idx.remove("a")
        route = idx.patrol_route()
        self.assertEqual(route, [(SlotRef(0, 0), None)])

    def test_patrol_route_maps_slot_to_correct_memory_id(self):
        idx = make_index(capacity=4)
        idx.assign("a")
        idx.assign("b")
        route = idx.patrol_route()
        mapping = dict(route)
        self.assertEqual(mapping[SlotRef(0, 0)], "a")
        self.assertEqual(mapping[SlotRef(0, 1)], "b")


class PersistenceTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        import tempfile
        idx = make_index(capacity=2)
        idx.assign("a")
        idx.assign("b")
        idx.assign("c")
        idx.remove("a")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spatial.json"
            idx.save(path)
            loaded = SpatialIndex.load(path)
        self.assertEqual(loaded.config.room_capacity, 2)
        self.assertEqual(loaded.room_count(), idx.room_count())
        self.assertEqual(loaded.patrol_route(), idx.patrol_route())
        self.assertIsNone(loaded.slot_of("a"))
        self.assertEqual(loaded.slot_of("b"), SlotRef(0, 1))

    def test_load_missing_file_returns_fresh_index(self):
        idx = SpatialIndex.load(Path("tests/_does_not_exist_spatial.json"))
        self.assertEqual(idx.room_count(), 0)


if __name__ == "__main__":
    unittest.main()
