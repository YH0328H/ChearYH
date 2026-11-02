import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.retrieval import BM25, Document, RetrievalResult, rrf_fusion  # noqa: E402


class BM25Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.docs = [
            Document("1", "今天天气很好", ["今天", "天气", "很", "好"]),
            Document("2", "天气不错适合出门", ["天气", "不错", "适合", "出门"]),
            Document("3", "明天会下雨", ["明天", "会", "下雨"]),
        ]
        self.bm25 = BM25(self.docs)

    def test_exact_match_ranks_first(self) -> None:
        results = self.bm25.search(["天气"], top_k=3)
        # Both doc 1 and 2 contain "天气", should rank higher than doc 3
        self.assertIn(results[0].doc_id, ["1", "2"])
        self.assertGreater(results[0].score, 0.0)

    def test_top_k_limits_results(self) -> None:
        results = self.bm25.search(["天气"], top_k=1)
        self.assertEqual(len(results), 1)

    def test_no_match_returns_zero_scores(self) -> None:
        results = self.bm25.search(["火星"], top_k=3)
        self.assertTrue(all(r.score == 0.0 for r in results))

    def test_multiple_query_terms_combine_scores(self) -> None:
        results = self.bm25.search(["天气", "今天"], top_k=3)
        # Doc 1 contains both terms, should rank first
        self.assertEqual(results[0].doc_id, "1")


class RRFTests(unittest.TestCase):
    def test_rrf_combines_two_lists(self) -> None:
        list1 = [RetrievalResult("1", 10.0), RetrievalResult("2", 5.0)]
        list2 = [RetrievalResult("2", 8.0), RetrievalResult("3", 4.0)]
        fused = rrf_fusion([list1, list2], k=60)
        # Doc 2 appears in both lists, should rank first
        self.assertEqual(fused[0].doc_id, "2")

    def test_rrf_with_single_list_preserves_order(self) -> None:
        list1 = [RetrievalResult("1", 10.0), RetrievalResult("2", 5.0)]
        fused = rrf_fusion([list1], k=60)
        self.assertEqual([r.doc_id for r in fused], ["1", "2"])

    def test_rrf_empty_lists_returns_empty(self) -> None:
        fused = rrf_fusion([], k=60)
        self.assertEqual(fused, [])


if __name__ == "__main__":
    unittest.main()
