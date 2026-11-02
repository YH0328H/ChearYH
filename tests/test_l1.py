import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l1 import CandidatePool, L1Archive, L1Record  # noqa: E402

NOW = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


class CandidatePoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pool = CandidatePool(Path(tempfile.mkdtemp()) / "pool.json", capacity=3, ttl_seconds=3600)

    def test_add_returns_false_when_full(self) -> None:
        self.assertTrue(self.pool.add("n1", None, None, [], NOW))
        self.assertTrue(self.pool.add("n2", None, None, [], NOW))
        self.assertTrue(self.pool.add("n3", None, None, [], NOW))
        self.assertFalse(self.pool.add("n4", None, None, [], NOW))

    def test_expired_candidates_not_counted_toward_capacity(self) -> None:
        self.pool.add("n1", None, None, [], NOW)
        later = NOW + timedelta(hours=2)
        self.assertEqual(len(self.pool.list_pending(later)), 0)
        self.assertTrue(self.pool.add("n2", None, None, [], later))

    def test_remove_clears_candidate(self) -> None:
        self.pool.add("n1", "calm", "user", ["id1"], NOW)
        self.pool.remove("n1", NOW)
        self.assertEqual(len(self.pool.list_pending(NOW)), 0)

    def test_list_pending_excludes_expired(self) -> None:
        self.pool.add("n1", None, None, [], NOW)
        self.pool.add("n2", None, None, [], NOW + timedelta(minutes=30))
        later = NOW + timedelta(hours=1, minutes=15)
        self.assertEqual(len(self.pool.list_pending(later)), 1)


class L1ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = L1Archive(Path(tempfile.mkdtemp()) / "l1.jsonl")

    def test_append_and_read_all(self) -> None:
        r1 = L1Record(NOW, "用户提到了工作压力", "anxious", "user", ["l0-1", "l0-2"])
        r2 = L1Record(NOW + timedelta(minutes=5), "聊到了周末计划", "excited", None, ["l0-3"])
        self.log.append(r1)
        self.log.append(r2)
        records = self.log.read_all()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].narrative, "用户提到了工作压力")
        self.assertEqual(records[1].emotion_tag, "excited")

    def test_empty_archive_returns_empty_list(self) -> None:
        self.assertEqual(self.log.read_all(), [])


if __name__ == "__main__":
    unittest.main()
