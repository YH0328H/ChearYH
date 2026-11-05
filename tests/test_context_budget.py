import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.context_budget import (  # noqa: E402
    BudgetConfig,
    ContextSegment,
    allocate_budget,
    load_budget_config,
)

CFG = load_budget_config(ROOT / "config" / "context_budget.toml")


class LoadConfigTests(unittest.TestCase):
    def test_loads_values_from_toml(self) -> None:
        self.assertEqual(CFG.persona_anchor, 400)
        self.assertEqual(CFG.recall_memory, 600)

    def test_missing_file_returns_defaults(self) -> None:
        cfg = load_budget_config(ROOT / "config" / "_does_not_exist.toml")
        self.assertEqual(cfg, BudgetConfig())

    def test_limit_for_unknown_category_raises(self) -> None:
        with self.assertRaises(ValueError):
            CFG.limit_for("not_a_category")


class SegmentValidationTests(unittest.TestCase):
    def test_unknown_category_raises(self) -> None:
        with self.assertRaises(ValueError):
            ContextSegment(category="nonexistent", text="x")


class PriorityArbitrationTests(unittest.TestCase):
    """核心验收：TASK.md 新增 32 —— 高低优先级同时超预算，低优先级被裁，高优先级完整保留。"""

    def test_high_priority_fully_kept_when_over_budget_overall(self) -> None:
        cfg = BudgetConfig(persona_anchor=10, recall_memory=10)
        candidates = [
            ContextSegment(category="persona_anchor", text="0123456789", timestamp=1.0),  # 恰好塞满
            ContextSegment(category="recall_memory", text="x" * 50, timestamp=2.0),  # 远超预算
        ]
        result = allocate_budget(candidates, cfg)
        kept_categories = {seg.category for seg in result.segments}
        self.assertIn("persona_anchor", kept_categories)
        self.assertNotIn("recall_memory", kept_categories)

    def test_low_priority_never_borrows_high_priority_remaining_budget(self) -> None:
        # persona_anchor 预算远未用完，但 recall_memory 不能借用它的余量。
        cfg = BudgetConfig(persona_anchor=1000, recall_memory=5)
        candidates = [
            ContextSegment(category="persona_anchor", text="short", timestamp=1.0),
            ContextSegment(category="recall_memory", text="this_is_too_long", timestamp=1.0),
        ]
        result = allocate_budget(candidates, cfg)
        kept_categories = {seg.category for seg in result.segments}
        self.assertIn("persona_anchor", kept_categories)
        self.assertNotIn("recall_memory", kept_categories)

    def test_same_category_prefers_more_recent_timestamp(self) -> None:
        cfg = BudgetConfig(mind_box=5)
        older = ContextSegment(category="mind_box", text="aaaaa", timestamp=1.0)
        newer = ContextSegment(category="mind_box", text="bbbbb", timestamp=2.0)
        result = allocate_budget([older, newer], cfg)
        kept_texts = {seg.text for seg in result.segments}
        self.assertEqual(kept_texts, {"bbbbb"})

    def test_segment_is_dropped_whole_not_truncated_mid_sentence(self) -> None:
        cfg = BudgetConfig(hard_boundary=3)
        seg = ContextSegment(category="hard_boundary", text="不可以", timestamp=1.0)
        result = allocate_budget([seg], cfg)
        # "不可以" 3 字符，恰好等于预算，应完整保留（不会被截成"不可"再塞入）
        self.assertEqual(result.segments[0].text, "不可以")

    def test_oversized_segment_dropped_entirely_when_exceeding_limit(self) -> None:
        cfg = BudgetConfig(hard_boundary=2)
        seg = ContextSegment(category="hard_boundary", text="不可以", timestamp=1.0)
        result = allocate_budget([seg], cfg)
        self.assertEqual(result.segments, [])
        self.assertFalse(result.decisions[0].kept)

    def test_decisions_are_observable_for_every_candidate(self) -> None:
        cfg = BudgetConfig()
        candidates = [
            ContextSegment(category="persona_anchor", text="hi", timestamp=1.0),
            ContextSegment(category="session_continuation", text="bye", timestamp=1.0),
        ]
        result = allocate_budget(candidates, cfg)
        self.assertEqual(len(result.decisions), len(candidates))
        for decision in result.decisions:
            self.assertIn(decision.reason, ("within_budget", "exceeds_remaining_category_budget"))

    def test_output_order_follows_priority_not_input_order(self) -> None:
        cfg = BudgetConfig()
        candidates = [
            ContextSegment(category="recall_memory", text="low", timestamp=1.0),
            ContextSegment(category="persona_anchor", text="high", timestamp=1.0),
        ]
        result = allocate_budget(candidates, cfg)
        categories_in_order = [seg.category for seg in result.segments]
        self.assertEqual(categories_in_order, ["persona_anchor", "recall_memory"])

    def test_rendered_text_joins_kept_segments(self) -> None:
        cfg = BudgetConfig()
        candidates = [
            ContextSegment(category="persona_anchor", text="锚点文本", timestamp=1.0),
            ContextSegment(category="mind_box", text="心事文本", timestamp=1.0),
        ]
        result = allocate_budget(candidates, cfg)
        rendered = result.rendered_text()
        self.assertIn("锚点文本", rendered)
        self.assertIn("心事文本", rendered)
        self.assertLess(rendered.index("锚点文本"), rendered.index("心事文本"))

    def test_categories_do_not_share_budget_pool(self) -> None:
        # 两个不同 category 各自预算充足时都应保留，验证互不借用也互不抢占。
        cfg = BudgetConfig(persona_anchor=5, hard_boundary=5)
        candidates = [
            ContextSegment(category="persona_anchor", text="aaaaa", timestamp=1.0),
            ContextSegment(category="hard_boundary", text="bbbbb", timestamp=1.0),
        ]
        result = allocate_budget(candidates, cfg)
        self.assertEqual(len(result.segments), 2)


if __name__ == "__main__":
    unittest.main()
