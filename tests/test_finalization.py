import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.finalization import FallbackStrategy, apply_fallback, decide_finalization  # noqa: E402


class FinalizationTests(unittest.TestCase):
    def test_valid_narrative_approved(self) -> None:
        decision = decide_finalization("用户问了工作的事", "calm", "user")
        self.assertTrue(decision.approved)
        self.assertEqual(decision.reason, "approved")

    def test_empty_narrative_rejected(self) -> None:
        decision = decide_finalization("", "calm", "user")
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "empty narrative")

    def test_whitespace_only_narrative_rejected(self) -> None:
        decision = decide_finalization("   ", "calm", "user")
        self.assertFalse(decision.approved)

    def test_empty_emotion_tag_rejected(self) -> None:
        decision = decide_finalization("narrative", "", "user")
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "empty emotion tag")

    def test_empty_relation_tag_rejected(self) -> None:
        decision = decide_finalization("narrative", "calm", "")
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "empty relation tag")

    def test_none_tags_accepted(self) -> None:
        decision = decide_finalization("narrative", None, None)
        self.assertTrue(decision.approved)


class FallbackTests(unittest.TestCase):
    def test_discard_strategy(self) -> None:
        self.assertEqual(apply_fallback(FallbackStrategy.DISCARD), "discard")

    def test_downgrade_strategy(self) -> None:
        self.assertEqual(apply_fallback(FallbackStrategy.DOWNGRADE), "downgrade_to_l0")

    def test_keep_strategy(self) -> None:
        self.assertEqual(apply_fallback(FallbackStrategy.KEEP), "keep_in_pool")


if __name__ == "__main__":
    unittest.main()
