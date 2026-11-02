import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.retrieval import (  # noqa: E402
    BM25,
    Document,
    EmbeddingConfig,
    EmbeddingError,
    RetrievalResult,
    VectorDocument,
    VectorRetrieval,
    cosine_similarity,
    embed_text,
    load_embedding_config,
    rrf_fusion,
)


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


class EmbeddingTests(unittest.TestCase):
    def test_embed_text_returns_vector(self) -> None:
        cfg = EmbeddingConfig("https://x.test/v1", "m-1", "k-test", 1024)
        seen = []

        def post(url, body, headers):
            seen.append((url, body["model"]))
            return {"data": [{"embedding": [0.1] * 1024}]}

        vector = embed_text(cfg, "test", post)
        self.assertEqual(len(vector), 1024)
        self.assertEqual(seen, [("https://x.test/v1/embeddings", "m-1")])

    def test_embed_missing_key_raises(self) -> None:
        cfg = EmbeddingConfig("https://x.test/v1", "m-1", "", 1024)
        with self.assertRaises(EmbeddingError):
            embed_text(cfg, "test", lambda u, b, h: {})

    def test_embed_wrong_dimensions_raises(self) -> None:
        cfg = EmbeddingConfig("https://x.test/v1", "m-1", "k-test", 1024)
        with self.assertRaises(EmbeddingError):
            embed_text(cfg, "test", lambda u, b, h: {"data": [{"embedding": [0.1] * 512}]})

    def test_load_embedding_config(self) -> None:
        path = Path(tempfile.mkdtemp()) / "embedding.toml"
        path.write_text(
            '[embedding]\nbase_url = "https://y.test"\nmodel_id = "m-2"\nkey_env = "TEST_KEY"\ndimensions = 512\n',
            encoding="utf-8",
        )
        cfg = load_embedding_config(path, {"TEST_KEY": "k-env"})
        self.assertEqual((cfg.base_url, cfg.model_id, cfg.api_key, cfg.dimensions),
                         ("https://y.test", "m-2", "k-env", 512))


class VectorTests(unittest.TestCase):
    def test_cosine_similarity(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 1.0)
        c = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, c), 0.0)

    def test_vector_search_ranks_by_similarity(self) -> None:
        docs = [
            VectorDocument("1", "天气", [1.0, 0.0, 0.0]),
            VectorDocument("2", "下雨", [0.9, 0.1, 0.0]),
            VectorDocument("3", "火星", [0.0, 0.0, 1.0]),
        ]
        retrieval = VectorRetrieval(docs)
        results = retrieval.search([1.0, 0.0, 0.0], top_k=3)
        self.assertEqual(results[0].doc_id, "1")
        self.assertGreater(results[0].score, results[2].score)


if __name__ == "__main__":
    unittest.main()

