import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.dedup import (  # noqa: E402
    DedupConfig,
    MergeCandidate,
    decide_merge,
    extract_numbers,
    jaccard_similarity,
    merge_near_duplicates,
    numbers_conflict,
)


class JaccardSimilarityTests(unittest.TestCase):
    def test_identical_text_is_one(self) -> None:
        self.assertAlmostEqual(jaccard_similarity("今天 天气 很 好", "今天 天气 很 好"), 1.0)

    def test_disjoint_text_is_zero(self) -> None:
        self.assertAlmostEqual(jaccard_similarity("今天 天气 好", "明天 下雨 冷"), 0.0)

    def test_both_empty_is_one(self) -> None:
        self.assertAlmostEqual(jaccard_similarity("", ""), 1.0)


class ExtractNumbersTests(unittest.TestCase):
    def test_extracts_integers(self) -> None:
        self.assertEqual(extract_numbers("21点到家"), {"21"})

    def test_extracts_decimals(self) -> None:
        self.assertEqual(extract_numbers("体温38.5度"), {"38.5"})

    def test_no_numbers_returns_empty_set(self) -> None:
        self.assertEqual(extract_numbers("没有数字"), set())


class NumbersConflictTests(unittest.TestCase):
    def test_same_numbers_no_conflict(self) -> None:
        self.assertFalse(numbers_conflict("21点到家", "21点才到家"))

    def test_different_numbers_conflict(self) -> None:
        self.assertTrue(numbers_conflict("21点到家", "21点30到家"))

    def test_no_numbers_either_side_no_conflict(self) -> None:
        self.assertFalse(numbers_conflict("今天很开心", "今天心情不错"))


class DecideMergeTests(unittest.TestCase):
    def test_merges_highly_similar_text_without_numbers(self) -> None:
        a = MergeCandidate(id="a", text="今天 天气 很 好 心情 不错")
        b = MergeCandidate(id="b", text="今天 天气 很 好 心情 不错 呢")
        decision = decide_merge(a, b, DedupConfig(similarity_threshold=0.7))
        self.assertTrue(decision.merged)
        self.assertEqual(decision.kept_id, "a")

    def test_does_not_merge_below_threshold(self) -> None:
        a = MergeCandidate(id="a", text="今天 天气 好")
        b = MergeCandidate(id="b", text="明天 下雨 冷")
        decision = decide_merge(a, b)
        self.assertFalse(decision.merged)
        self.assertEqual(decision.reason, "below_threshold")

    def test_number_protection_blocks_merge_even_if_similar(self) -> None:
        a = MergeCandidate(id="a", text="约 21 点 到家 吃饭")
        b = MergeCandidate(id="b", text="约 21.30 点 到家 吃饭")
        decision = decide_merge(a, b, DedupConfig(similarity_threshold=0.5))
        self.assertFalse(decision.merged)
        self.assertEqual(decision.reason, "numbers_conflict")

    def test_flash_weight_node_never_merges(self) -> None:
        a = MergeCandidate(id="a", text="今天 天气 很 好", flash_weight=True)
        b = MergeCandidate(id="b", text="今天 天气 很 好")
        decision = decide_merge(a, b)
        self.assertFalse(decision.merged)
        self.assertEqual(decision.reason, "flash_weight_excluded")

    def test_flash_weight_takes_priority_over_number_conflict_check(self) -> None:
        a = MergeCandidate(id="a", text="约 21 点", flash_weight=True)
        b = MergeCandidate(id="b", text="约 22 点")
        decision = decide_merge(a, b)
        self.assertEqual(decision.reason, "flash_weight_excluded")


class MergeNearDuplicatesTests(unittest.TestCase):
    def test_merges_chain_of_similar_candidates(self) -> None:
        candidates = [
            MergeCandidate(id="a", text="今天 天气 很 好 心情 不错"),
            MergeCandidate(id="b", text="今天 天气 很 好 心情 不错 呢"),
            MergeCandidate(id="c", text="完全 不同 的 内容 在 这里"),
        ]
        kept, decisions = merge_near_duplicates(candidates, DedupConfig(similarity_threshold=0.7))
        kept_ids = {c.id for c in kept}
        self.assertEqual(kept_ids, {"a", "c"})
        self.assertTrue(any(d.merged for d in decisions))

    def test_flash_weight_candidate_always_kept(self) -> None:
        candidates = [
            MergeCandidate(id="a", text="今天 天气 很 好", flash_weight=True),
            MergeCandidate(id="b", text="今天 天气 很 好", flash_weight=True),
        ]
        kept, _ = merge_near_duplicates(candidates)
        self.assertEqual({c.id for c in kept}, {"a", "b"})

    def test_empty_input_returns_empty(self) -> None:
        kept, decisions = merge_near_duplicates([])
        self.assertEqual(kept, [])
        self.assertEqual(decisions, [])

    def test_single_candidate_always_kept(self) -> None:
        kept, decisions = merge_near_duplicates([MergeCandidate(id="a", text="任意文本")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(decisions, [])


if __name__ == "__main__":
    unittest.main()
