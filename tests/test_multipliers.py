import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.multipliers import (  # noqa: E402
    MultiplierConfig,
    apply_multipliers,
    drive_bias,
    jitter,
    lifecycle_multiplier,
    region_bonus,
    rumination_suppression,
    valence_bias,
)


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_fresh_memory_is_max(self) -> None:
        mult = lifecycle_multiplier(elapsed_seconds=0, min_mult=0.5)
        self.assertAlmostEqual(mult, 1.0)

    def test_lifecycle_old_memory_approaches_min(self) -> None:
        mult = lifecycle_multiplier(elapsed_seconds=86400 * 30, tau=86400 * 7, min_mult=0.5)
        self.assertLess(mult, 0.7)
        self.assertGreater(mult, 0.5)


class RuminationTests(unittest.TestCase):
    def test_low_recall_count_no_penalty(self) -> None:
        mult = rumination_suppression(recall_count=2, threshold=5, penalty=0.6)
        self.assertEqual(mult, 1.0)

    def test_high_recall_count_applies_penalty(self) -> None:
        mult = rumination_suppression(recall_count=6, threshold=5, penalty=0.6)
        self.assertEqual(mult, 0.6)


class DriveBiasTests(unittest.TestCase):
    def test_active_drive_boosts_related_memory(self) -> None:
        tags = ["curiosity", "user"]
        drives = {"seeking": 0.8, "affiliation": 0.5}
        tag_map = {"curiosity": "seeking", "user": "affiliation"}
        mult = drive_bias(tags, drives, tag_map)
        # Boost = 1 + 0.8 + 0.5 = 2.3
        self.assertAlmostEqual(mult, 2.3)

    def test_no_matching_drive_no_boost(self) -> None:
        tags = ["unknown"]
        drives = {"seeking": 0.8}
        tag_map = {"curiosity": "seeking"}
        mult = drive_bias(tags, drives, tag_map)
        self.assertEqual(mult, 1.0)


class ValenceBiasTests(unittest.TestCase):
    def test_similar_valence_boosts_score(self) -> None:
        # Both positive
        mult = valence_bias(memory_valence=0.8, current_valence=0.7, alignment_boost=1.5)
        self.assertGreater(mult, 1.0)

    def test_opposite_valence_reduces_boost(self) -> None:
        # Opposite signs
        mult_opposite = valence_bias(memory_valence=0.8, current_valence=-0.8, alignment_boost=1.5)
        mult_similar = valence_bias(memory_valence=0.8, current_valence=0.7, alignment_boost=1.5)
        self.assertLess(mult_opposite, mult_similar)


class RegionBonusTests(unittest.TestCase):
    def test_matching_region_gets_bonus(self) -> None:
        mult = region_bonus(memory_region="work", current_region="work", bonus=1.2)
        self.assertEqual(mult, 1.2)

    def test_non_matching_region_no_bonus(self) -> None:
        mult = region_bonus(memory_region="work", current_region="home", bonus=1.2)
        self.assertEqual(mult, 1.0)


class JitterTests(unittest.TestCase):
    def test_jitter_is_near_one(self) -> None:
        mult = jitter(jitter_range=0.1)
        self.assertGreater(mult, 0.9)
        self.assertLess(mult, 1.1)


class ApplyMultipliersTests(unittest.TestCase):
    def test_apply_all_multipliers(self) -> None:
        config = MultiplierConfig(
            lifecycle_min=0.5,
            rumination_threshold=5,
            rumination_penalty=0.6,
            jitter_range=0.0,  # Disable jitter for deterministic test
            region_bonus=1.2,
        )
        score = apply_multipliers(
            base_score=10.0,
            elapsed_seconds=0,  # Fresh → lifecycle=1.0
            recall_count=2,  # Low → rumination=1.0
            memory_tags=["curiosity"],
            active_drives={"seeking": 0.5},
            tag_drive_map={"curiosity": "seeking"},
            memory_valence=0.5,
            current_valence=0.5,  # Matching → valence≈1.25
            memory_region="work",
            current_region="work",  # Matching → region=1.2
            config=config,
        )
        # Base 10 × lifecycle(1.0) × rumination(1.0) × drive(1.5) × valence(≈1.25) × region(1.2) × jitter(1.0)
        # ≈ 10 × 1.5 × 1.25 × 1.2 = 22.5
        self.assertGreater(score, 20.0)
        self.assertLess(score, 30.0)  # Allow some margin for valence calculation


if __name__ == "__main__":
    unittest.main()
