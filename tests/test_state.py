import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.state import (  # noqa: E402
    FourWill,
    SixDrives,
    compute_surprise,
    ebbinghaus_decay,
    inertial_filter,
    project_six_drives_to_four_will,
    translate_to_texture,
    weibull_decay,
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
        drives = SixDrives(seeking=0.8, affiliation=0.6, competence=0.7, certainty=0.9, care=0.5, play=0.4)
        will = project_six_drives_to_four_will(drives, social_battery_current=0.75)
        # connection_desire = affiliation*0.7 + care*0.3 = 0.6*0.7 + 0.5*0.3 = 0.42 + 0.15 = 0.57
        self.assertAlmostEqual(will.connection_desire, 0.57, places=2)
        # expression_impulse = seeking*0.4 + competence*0.4 + play*0.2 = 0.8*0.4 + 0.7*0.4 + 0.4*0.2 = 0.68
        self.assertAlmostEqual(will.expression_impulse, 0.68, places=2)
        # security = certainty*0.8 - seeking*0.2 = 0.9*0.8 - 0.8*0.2 = 0.72 - 0.16 = 0.56
        self.assertAlmostEqual(will.security, 0.56, places=2)
        self.assertEqual(will.social_battery, 0.75)

    def test_default_drives_give_moderate_will(self) -> None:
        drives = SixDrives()  # All defaults = 0.5
        will = project_six_drives_to_four_will(drives)
        self.assertGreater(will.connection_desire, 0.0)
        self.assertLess(will.connection_desire, 1.0)

    def test_high_seeking_reduces_security(self) -> None:
        high_seeking = SixDrives(seeking=0.9, certainty=0.5)
        low_seeking = SixDrives(seeking=0.1, certainty=0.5)
        will_high = project_six_drives_to_four_will(high_seeking)
        will_low = project_six_drives_to_four_will(low_seeking)
        # High seeking should reduce security more
        self.assertLess(will_high.security, will_low.security)


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


class DecayTests(unittest.TestCase):
    def test_ebbinghaus_decay_at_zero_time_is_unchanged(self) -> None:
        weight = ebbinghaus_decay(initial_weight=1.0, elapsed_seconds=0, tau=86400 * 7)
        self.assertAlmostEqual(weight, 1.0)

    def test_ebbinghaus_decay_at_one_tau_is_one_over_e(self) -> None:
        import math
        weight = ebbinghaus_decay(initial_weight=1.0, elapsed_seconds=86400 * 7, tau=86400 * 7)
        self.assertAlmostEqual(weight, 1.0 / math.e, places=5)

    def test_ebbinghaus_decay_reduces_weight_over_time(self) -> None:
        weight_day1 = ebbinghaus_decay(1.0, elapsed_seconds=86400, tau=86400 * 7)
        weight_day7 = ebbinghaus_decay(1.0, elapsed_seconds=86400 * 7, tau=86400 * 7)
        weight_day14 = ebbinghaus_decay(1.0, elapsed_seconds=86400 * 14, tau=86400 * 7)
        self.assertGreater(weight_day1, weight_day7)
        self.assertGreater(weight_day7, weight_day14)

    def test_weibull_decay_at_zero_time_is_unchanged(self) -> None:
        weight = weibull_decay(initial_weight=1.0, elapsed_seconds=0)
        self.assertAlmostEqual(weight, 1.0)

    def test_weibull_decay_reduces_weight_over_time(self) -> None:
        weight_day1 = weibull_decay(1.0, elapsed_seconds=86400)
        weight_day7 = weibull_decay(1.0, elapsed_seconds=86400 * 7)
        self.assertGreater(weight_day1, weight_day7)

    def test_weibull_with_k_less_than_1_decays_fast_initially(self) -> None:
        # k=0.8: fast initial decay
        weight_day1_fast = weibull_decay(1.0, elapsed_seconds=86400, k=0.8)
        # k=1.0: exponential (slower initial)
        weight_day1_exp = weibull_decay(1.0, elapsed_seconds=86400, k=1.0)
        # Fast decay should have lower weight after 1 day
        self.assertLess(weight_day1_fast, weight_day1_exp)


if __name__ == "__main__":
    unittest.main()
