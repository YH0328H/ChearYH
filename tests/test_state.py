import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.state import (  # noqa: E402
    FourWill,
    compute_surprise,
    inertial_filter,
    project_six_drives_to_four_will,
    translate_to_texture,
)


class SurpriseTests(unittest.TestCase):
    def test_surprise_with_no_history_is_max(self) -> None:
        self.assertEqual(compute_surprise("新事件", []), 1.0)

    def test_surprise_with_identical_history_is_min(self) -> None:
        surprise = compute_surprise("今天 天气 很 好", ["今天 天气 很 好"])
        self.assertAlmostEqual(surprise, 0.0)

    def test_surprise_with_partial_overlap_is_intermediate(self) -> None:
        surprise = compute_surprise("今天 天气 很 好", ["今天 天气 不错", "明天 会 下雨"])
        self.assertGreater(surprise, 0.3)
        self.assertLess(surprise, 0.9)


class InertialFilterTests(unittest.TestCase):
    def test_high_alpha_slow_transition(self) -> None:
        # alpha=0.9 means 90% inertia, slow change
        v = inertial_filter(current=0.2, target=0.8, alpha=0.9)
        self.assertGreater(v, 0.2)
        self.assertLess(v, 0.4)

    def test_low_alpha_fast_transition(self) -> None:
        # alpha=0.3 means 30% inertia, fast change
        v = inertial_filter(current=0.2, target=0.8, alpha=0.3)
        self.assertGreater(v, 0.5)
        self.assertLess(v, 0.8)

    def test_at_target_stays_at_target(self) -> None:
        v = inertial_filter(current=0.5, target=0.5, alpha=0.7)
        self.assertAlmostEqual(v, 0.5)


class FourWillTests(unittest.TestCase):
    def test_six_drives_to_four_will_projection(self) -> None:
        drives = {"curiosity": 0.8, "social": 0.6, "novelty": 0.3, "safety": 0.9}
        will = project_six_drives_to_four_will(drives)
        self.assertGreater(will.connection_desire, 0.5)  # High curiosity + social
        self.assertGreater(will.security, 0.7)  # High safety

    def test_default_drives_give_moderate_will(self) -> None:
        will = project_six_drives_to_four_will({})
        self.assertGreater(will.connection_desire, 0.0)
        self.assertLess(will.connection_desire, 1.0)


class TextureTests(unittest.TestCase):
    def test_high_social_battery_translates_to_energetic(self) -> None:
        texture = translate_to_texture("social_battery", 0.8)
        self.assertIn("精力", texture)

    def test_low_social_battery_translates_to_tired(self) -> None:
        texture = translate_to_texture("social_battery", 0.1)
        self.assertIn("累", texture)

    def test_unknown_dimension_returns_numeric(self) -> None:
        texture = translate_to_texture("unknown", 0.5)
        self.assertIn("0.50", texture)


if __name__ == "__main__":
    unittest.main()
