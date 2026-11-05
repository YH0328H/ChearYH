import random
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.idle import (  # noqa: E402
    ActionAmplitude,
    BornRuleConfig,
    born_probabilities,
    default_idle_amplitudes,
    sample_action,
)


class BornProbabilitiesTests(unittest.TestCase):
    def test_probabilities_sum_to_one(self) -> None:
        amps = [ActionAmplitude("看书", 0.6), ActionAmplitude("发呆", 0.8)]
        probs = born_probabilities(amps)
        self.assertAlmostEqual(sum(probs.values()), 1.0)

    def test_probability_is_magnitude_squared_normalized(self) -> None:
        amps = [ActionAmplitude("a", 1.0), ActionAmplitude("b", 1.0)]
        probs = born_probabilities(amps)
        self.assertAlmostEqual(probs["a"], 0.5)
        self.assertAlmostEqual(probs["b"], 0.5)

    def test_higher_magnitude_gives_higher_probability(self) -> None:
        amps = [ActionAmplitude("a", 0.9), ActionAmplitude("b", 0.1)]
        probs = born_probabilities(amps)
        self.assertGreater(probs["a"], probs["b"])

    def test_all_zero_amplitudes_splits_evenly(self) -> None:
        amps = [ActionAmplitude("a", 0.0), ActionAmplitude("b", 0.0)]
        probs = born_probabilities(amps)
        self.assertAlmostEqual(probs["a"], 0.5)
        self.assertAlmostEqual(probs["b"], 0.5)

    def test_empty_list_returns_empty_dict(self) -> None:
        self.assertEqual(born_probabilities([]), {})


class SampleActionTests(unittest.TestCase):
    def test_single_action_always_selected(self) -> None:
        amps = [ActionAmplitude("看书", 1.0)]
        rng = random.Random(1)
        self.assertEqual(sample_action(amps, rng=rng), "看书")

    def test_zero_amplitude_action_never_selected_over_many_draws(self) -> None:
        amps = [ActionAmplitude("有", 1.0), ActionAmplitude("无", 0.0)]
        rng = random.Random(42)
        results = [sample_action(amps, rng=rng) for _ in range(200)]
        self.assertNotIn("无", results)

    def test_distribution_roughly_matches_probabilities(self) -> None:
        amps = [ActionAmplitude("a", 0.9), ActionAmplitude("b", 0.1)]
        rng = random.Random(7)
        results = [sample_action(amps, rng=rng) for _ in range(2000)]
        counts = Counter(results)
        # P(a) = 0.9^2/(0.9^2+0.1^2) = 0.81/0.82 ≈ 0.9878
        ratio_a = counts["a"] / len(results)
        self.assertGreater(ratio_a, 0.9)

    def test_empty_amplitudes_returns_none(self) -> None:
        self.assertIsNone(sample_action([], rng=random.Random(1)))

    def test_below_threshold_action_excluded(self) -> None:
        cfg = BornRuleConfig(min_probability_threshold=0.5)
        amps = [ActionAmplitude("主", 10.0), ActionAmplitude("次", 0.1)]
        rng = random.Random(3)
        results = [sample_action(amps, rng=rng, config=cfg) for _ in range(50)]
        self.assertNotIn("次", results)


class DefaultIdleAmplitudesTests(unittest.TestCase):
    def test_high_connection_and_impulse_favors_chat(self) -> None:
        amps = default_idle_amplitudes(social_battery=0.6, connection_desire=0.9, expression_impulse=0.9)
        probs = born_probabilities(amps)
        self.assertGreater(probs["搭话"], probs["看书"])
        self.assertGreater(probs["搭话"], probs["发呆"])

    def test_low_battery_favors_daze(self) -> None:
        amps = default_idle_amplitudes(social_battery=0.05, connection_desire=0.1, expression_impulse=0.1)
        probs = born_probabilities(amps)
        self.assertGreater(probs["发呆"], probs["搭话"])

    def test_high_battery_low_connection_favors_reading(self) -> None:
        amps = default_idle_amplitudes(social_battery=0.9, connection_desire=0.05, expression_impulse=0.5)
        probs = born_probabilities(amps)
        self.assertGreater(probs["看书"], probs["搭话"])

    def test_returns_three_named_actions(self) -> None:
        amps = default_idle_amplitudes(0.5, 0.5, 0.5)
        names = {a.name for a in amps}
        self.assertEqual(names, {"看书", "发呆", "搭话"})


if __name__ == "__main__":
    unittest.main()
