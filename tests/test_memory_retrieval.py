from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l0 import L0Archive
from cether.memory_retrieval import (
    L0RetrievalService, RetrievalConfig, RetrievalConfigWatcher, tokenize, weighted_rrf_fusion,
)
from cether.retrieval import GraphEdge, GraphNode, KnowledgeGraph, RetrievalResult
from cether.roles import RoleRegistry, ScopeMismatchError


class MemoryRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.registry = RoleRegistry(self.tmp / "registry.json")
        self.config = RetrievalConfigWatcher(self.tmp / "missing.toml", RetrievalConfig(jitter_range=0.0))
        self.role = self.registry.create_role("A", self.tmp / "role-a")
        self.other = self.registry.create_role("B", self.tmp / "role-b")
        self.registry.switch(self.role.role_id)
        self.role = self.registry.active
        self.archive = L0Archive(self.role.workspace / "memory" / "l0.jsonl")
        self.archive.append("用户喜欢喝茉莉花茶", "conversation")
        self.archive.append("天气预报说明天有雨", "conversation")
        self.archive.append("秘密低权重记录茉莉", "conversation", weight="low")
        self.service = L0RetrievalService(self.role, self.registry, self.archive, self.config)

    def test_query_returns_relevant_positive_matches_not_recent_tail(self) -> None:
        results = self.service.search("茉莉花茶")
        self.assertEqual(results, ("用户喜欢喝茉莉花茶",))
        self.assertEqual(self.service.last_observation.result_count, 1)
        self.assertEqual(self.service.last_observation.channel, "lexical")

    def test_no_match_returns_empty_instead_of_zero_score_documents(self) -> None:
        self.assertEqual(self.service.search("火星飞船"), ())

    def test_low_weight_archive_records_are_not_proactively_injected(self) -> None:
        self.assertNotIn("秘密低权重记录茉莉", self.service.search("秘密低权重记录茉莉"))

    def test_scope_mismatch_propagates_before_archive_read(self) -> None:
        self.registry.switch(self.other.role_id)
        with self.assertRaises(ScopeMismatchError):
            self.service.search("茉莉")

    def test_archive_failure_is_observable_empty_result(self) -> None:
        class BrokenArchive:
            def __iter__(self):
                raise OSError("archive unavailable")
        service = L0RetrievalService(self.role, self.registry, BrokenArchive(), self.config)
        self.assertEqual(service.search("茉莉"), ())
        self.assertIn("archive unavailable", service.last_observation.error)

    def test_latency_budget_is_reported(self) -> None:
        now = [10.0]
        def clock():
            value = now[0]
            now[0] += 0.1
            return value
        service = L0RetrievalService(self.role, self.registry, self.archive, self.config,
                                     clock=clock)
        service.search("茉莉")
        self.assertAlmostEqual(service.last_observation.elapsed_ms, 200.0)
        self.assertFalse(service.last_observation.budget_exceeded)

    def test_tokenizer_creates_chinese_bigrams_and_casefolds_latin(self) -> None:
        tokens = tokenize("Hello 天气晴朗")
        self.assertIn("hello", tokens)
        self.assertIn("天气", tokens)
        self.assertIn("气晴", tokens)

    def test_config_watcher_reloads_valid_change_and_keeps_last_good_on_invalid(self) -> None:
        path = self.tmp / "retrieval.toml"
        path.write_text("[retrieval]\ntop_k=2\nlatency_budget_ms=120\n", encoding="utf-8")
        watcher = RetrievalConfigWatcher(path)
        self.assertEqual(watcher.get().top_k, 2)
        path.write_text("[retrieval]\ntop_k=4\nlatency_budget_ms=200\n", encoding="utf-8")
        self.assertEqual(watcher.get().top_k, 4)
        path.write_text("[retrieval\n", encoding="utf-8")
        self.assertEqual(watcher.get().top_k, 4)

    def test_weighted_rrf_combines_channels_and_applies_channel_weights(self) -> None:
        fused = weighted_rrf_fusion(
            [[RetrievalResult("lexical", 1), RetrievalResult("shared", 0.5)],
             [RetrievalResult("shared", 1), RetrievalResult("vector", 0.5)]],
            [1.0, 2.0], k=1,
        )
        self.assertEqual(fused[0].doc_id, "shared")

    def test_vector_and_graph_channels_are_fused_and_observable(self) -> None:
        first, second = [record for record in self.archive if record["weight"] == "normal"]
        vectors = {first["id"]: [1.0, 0.0], second["id"]: [0.0, 1.0]}
        def graph_provider(records):
            nodes = [GraphNode(str(index), token, [str(record["id"])])
                     for index, record in enumerate(records)
                     for token in set(tokenize(record["text"]))]
            return KnowledgeGraph(nodes, [GraphEdge("天气", "茉莉", 1.0)])
        service = L0RetrievalService(
            self.role, self.registry, self.archive, self.config,
            embedding_provider=lambda texts: [[1.0, 0.0] if "茉莉" in text else [0.0, 1.0] for text in texts],
            graph_provider=graph_provider,
        )
        results = service.search("茉莉花茶")
        self.assertIn("vector", service.last_observation.channel)
        self.assertIn("graph", service.last_observation.channel)
        self.assertGreater(service.last_observation.vector_count, 0)
        self.assertGreater(service.last_observation.graph_count, 0)
        self.assertEqual(results[0], first["text"])

    def test_archive_append_invalidates_cached_index(self) -> None:
        first = self.archive.append("stable unique phrase", "test")
        self.assertIn("stable unique phrase", self.service.search("stable unique"))
        second = self.archive.append("new appended phrase", "test")
        self.assertIn("new appended phrase", self.service.search("appended phrase"))
        self.assertNotEqual(first, second)

    def test_high_weight_requires_explicit_spatial_provider(self) -> None:
        import json
        high_id = "high-relationship"
        with self.archive.path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps({"id": high_id, "ts": "2026-11-07T00:00:00+00:00", "source": "test", "weight": 0.9, "text": "重要关系事件：一起庆祝生日"}, ensure_ascii=False) + "\n")
        without_spatial = self.service.search("生日")
        self.assertNotIn("重要关系事件：一起庆祝生日", without_spatial)
        service = L0RetrievalService(
            self.role, self.registry, self.archive, self.config,
            spatial_provider=lambda _query, records: [RetrievalResult(high_id, 1.0)],
        )
        self.assertEqual(service.search("生日")[0], "重要关系事件：一起庆祝生日")

    def test_lifecycle_and_repeat_suppression_change_rank_scores(self) -> None:
        old_id = self.archive.append("共同旅行去过京都", "conversation")
        fresh_id = self.archive.append("共同旅行去了京都", "conversation")
        service = L0RetrievalService(self.role, self.registry, self.archive, self.config,
                                     clock=lambda: 2_000_000_000.0)
        service.search("共同旅行 京都")
        scores = {result.doc_id: result.score for result in service.last_results}
        self.assertIn(old_id, scores)
        self.assertIn(fresh_id, scores)
        self.assertGreater(scores[fresh_id], 0.0)
        service.search("共同旅行 京都")
        self.assertTrue(all(result.score > 0 for result in service.last_results))


if __name__ == "__main__":
    unittest.main()
