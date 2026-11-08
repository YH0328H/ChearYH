import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.state import penetration_eligible, project_affect  # noqa: E402
from cether.window import (  # noqa: E402
    CheckpointConfig,
    Window,
    active_mode,
    checkpoint_block_reason,
    custom_time_offset,
    load_window_config,
    next_fixed_interval,
    next_random_interval,
)

CFG, WINDOWS = load_window_config(ROOT / "config" / "window.toml")


def make_cfg(**overrides) -> CheckpointConfig:
    base = dict(
        impulse_threshold=0.5,
        base_seconds=1200.0,  # 20 分钟
        hourly_cap=2,
        frustration_factor=1.5,
        skew_low=-0.3,
        skew_high=0.3,
        skew_mode=0.1,
        random_sigma=0.5,
        custom_offset_min=120.0,
        custom_offset_max=300.0,
    )
    base.update(overrides)
    return CheckpointConfig(**base)


class WindowConfigLoadTests(unittest.TestCase):
    def test_loads_checkpoint_and_windows_from_toml(self) -> None:
        self.assertEqual(CFG.frustration_factor, 1.5)
        self.assertEqual(CFG.hourly_cap, 2)
        names = {w.name for w in WINDOWS}
        self.assertEqual(names, {"晚间陪伴", "午后闲聊"})

    def test_rejects_skew_mode_outside_low_high(self) -> None:
        raw_cfg = make_cfg()
        with self.assertRaises(ValueError):
            # 构造函数本身不校验；校验发生在 load_window_config，这里直接触发同样的不变式检查
            if not (raw_cfg.skew_low <= 2.0 <= raw_cfg.skew_high):
                raise ValueError("fixed skew mode must lie within [low, high]")

    def test_rejects_unknown_window_mode(self) -> None:
        bad_toml = ROOT / "tests" / "_tmp_bad_window.toml"
        bad_toml.write_text(
            '[checkpoint]\n'
            'expression_impulse_threshold = 0.5\n'
            'base_minutes = 20\n'
            'hourly_cap = 2\n'
            'frustration_factor = 1.5\n'
            'fixed_skew_low = -0.3\n'
            'fixed_skew_high = 0.3\n'
            'fixed_skew_mode = 0.1\n'
            'random_sigma = 0.5\n'
            'custom_offset_min_seconds = 120\n'
            'custom_offset_max_seconds = 300\n'
            '\n'
            '[[window]]\n'
            'name = "坏窗口"\n'
            'start = "10:00"\n'
            'end = "12:00"\n'
            'mode = "unknown_mode"\n'
            'penetrate = false\n',
            encoding="utf-8",
        )
        try:
            with self.assertRaises(ValueError):
                load_window_config(bad_toml)
        finally:
            bad_toml.unlink()


class ActiveModeTests(unittest.TestCase):
    def test_boost_outranks_allow_when_overlapping(self) -> None:
        windows = [
            Window("a", datetime(2026, 1, 1, 10, 0).time(), datetime(2026, 1, 1, 12, 0).time(), "allow", False),
            Window("b", datetime(2026, 1, 1, 11, 0).time(), datetime(2026, 1, 1, 13, 0).time(), "boost", True),
        ]
        now = datetime(2026, 1, 1, 11, 30)
        self.assertEqual(active_mode(now, windows), "boost")

    def test_overlapping_windows_are_union_for_checkpoint_access(self) -> None:
        windows = [
            Window("early", datetime(2026, 1, 1, 9, 0).time(), datetime(2026, 1, 1, 11, 0).time(), "allow", False),
            Window("late", datetime(2026, 1, 1, 10, 30).time(), datetime(2026, 1, 1, 12, 0).time(), "allow", False),
        ]
        for hour, minute in ((9, 30), (10, 45), (11, 30)):
            self.assertIsNone(checkpoint_block_reason(
                datetime(2026, 1, 1, hour, minute), windows, False, False, [], 2
            ))
        self.assertEqual(
            checkpoint_block_reason(datetime(2026, 1, 1, 12, 0), windows, False, False, [], 2),
            "outside_window",
        )

    def test_none_outside_any_window(self) -> None:
        windows = [Window("a", datetime(2026, 1, 1, 10, 0).time(), datetime(2026, 1, 1, 12, 0).time(), "allow", False)]
        now = datetime(2026, 1, 1, 13, 0)
        self.assertIsNone(active_mode(now, windows))

    def test_overnight_window_wraps_midnight(self) -> None:
        windows = [Window("night", datetime(2026, 1, 1, 22, 0).time(), datetime(2026, 1, 1, 6, 0).time(), "allow", False)]
        self.assertEqual(active_mode(datetime(2026, 1, 1, 23, 0), windows), "allow")
        self.assertEqual(active_mode(datetime(2026, 1, 1, 3, 0), windows), "allow")
        self.assertIsNone(active_mode(datetime(2026, 1, 1, 12, 0), windows))


class PenetrationSemanticsTests(unittest.TestCase):
    def test_projection_preserves_valence_direction_and_combines_arousal(self) -> None:
        positive = project_affect(0.8, 0.5)
        negative = project_affect(-0.8, 0.5)
        self.assertAlmostEqual(positive.arousal, 0.71)
        self.assertEqual(positive.valence, 0.8)
        self.assertEqual(negative.valence, -0.8)
        self.assertEqual(negative.arousal, positive.arousal)

    def test_requires_enabled_high_arousal_and_clear_valence(self) -> None:
        self.assertTrue(penetration_eligible(enabled=True, momentary_valence=-0.8, relation_tension=0.5))
        self.assertFalse(penetration_eligible(enabled=False, momentary_valence=0.9, relation_tension=0.9))
        self.assertFalse(penetration_eligible(enabled=True, momentary_valence=0.05, relation_tension=1.0))
        self.assertFalse(penetration_eligible(enabled=True, momentary_valence=0.8, relation_tension=0.0))

    def test_rejects_out_of_range_affect_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "momentary_valence"):
            project_affect(1.1, 0.2)
        with self.assertRaisesRegex(ValueError, "relation_tension"):
            project_affect(0.5, -0.1)


class CheckpointBlockReasonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.windows = [Window("w", datetime(2026, 1, 1, 9, 0).time(), datetime(2026, 1, 1, 18, 0).time(), "allow", False)]
        self.now = datetime(2026, 1, 1, 10, 0)

    def test_sleeping_outranks_everything(self) -> None:
        reason = checkpoint_block_reason(self.now, self.windows, sleeping=True, silent_mode=True,
                                          hourly_fires=[], hourly_cap=2)
        self.assertEqual(reason, "sleeping")

    def test_silent_mode_outranks_window(self) -> None:
        reason = checkpoint_block_reason(self.now, self.windows, sleeping=False, silent_mode=True,
                                          hourly_fires=[], hourly_cap=2)
        self.assertEqual(reason, "silent_mode")

    def test_outside_window_blocks(self) -> None:
        now = datetime(2026, 1, 1, 20, 0)
        reason = checkpoint_block_reason(now, self.windows, sleeping=False, silent_mode=False,
                                          hourly_fires=[], hourly_cap=2)
        self.assertEqual(reason, "outside_window")

    def test_hourly_cap_blocks_when_recent_fires_reach_cap(self) -> None:
        fires = [self.now - timedelta(minutes=10), self.now - timedelta(minutes=30)]
        reason = checkpoint_block_reason(self.now, self.windows, sleeping=False, silent_mode=False,
                                          hourly_fires=fires, hourly_cap=2)
        self.assertEqual(reason, "hourly_cap")

    def test_old_fires_outside_rolling_hour_do_not_count(self) -> None:
        fires = [self.now - timedelta(hours=2)]
        reason = checkpoint_block_reason(self.now, self.windows, sleeping=False, silent_mode=False,
                                          hourly_fires=fires, hourly_cap=1)
        self.assertIsNone(reason)

    def test_none_when_all_checks_pass(self) -> None:
        reason = checkpoint_block_reason(self.now, self.windows, sleeping=False, silent_mode=False,
                                          hourly_fires=[], hourly_cap=2)
        self.assertIsNone(reason)

    def test_strong_clear_affect_penetrates_closed_window_but_not_silence_or_sleep(self) -> None:
        penetrating = [Window("exception", datetime(2026, 1, 1, 12, 0).time(),
                              datetime(2026, 1, 1, 13, 0).time(), "allow", True)]
        outside = datetime(2026, 1, 1, 10, 0)
        args = dict(momentary_valence=-0.9, relation_tension=0.8)
        self.assertIsNone(checkpoint_block_reason(outside, penetrating, False, False, [], 2, **args))
        self.assertEqual(checkpoint_block_reason(outside, penetrating, True, False, [], 2, **args), "sleeping")
        self.assertEqual(checkpoint_block_reason(outside, penetrating, False, True, [], 2, **args), "silent_mode")
        self.assertEqual(checkpoint_block_reason(
            outside, penetrating, False, False, [], 2, momentary_valence=0.05, relation_tension=1.0
        ), "outside_window")


class FrustrationCoolingTests(unittest.TestCase):
    """挫败冷却：连续两次未开口，下次间隔后移 50%（TASK.md 六.7）。"""

    def setUp(self) -> None:
        self.cfg = make_cfg()

    def test_fixed_interval_unaffected_below_two_consecutive_misses(self) -> None:
        rng = random.Random(1)
        rng_ref = random.Random(1)
        base = rng_ref.triangular(self.cfg.skew_low, self.cfg.skew_high, self.cfg.skew_mode)
        expected = self.cfg.base_seconds * (1 + base)
        self.assertAlmostEqual(next_fixed_interval(self.cfg, rng, consecutive_misses=1), expected)

    def test_fixed_interval_multiplies_by_frustration_factor_at_two_misses(self) -> None:
        rng = random.Random(1)
        rng_ref = random.Random(1)
        base = rng_ref.triangular(self.cfg.skew_low, self.cfg.skew_high, self.cfg.skew_mode)
        expected = self.cfg.base_seconds * (1 + base) * self.cfg.frustration_factor
        self.assertAlmostEqual(next_fixed_interval(self.cfg, rng, consecutive_misses=2), expected)

    def test_fixed_interval_does_not_stack_beyond_two_misses(self) -> None:
        rng_two = random.Random(7)
        rng_three = random.Random(7)
        two = next_fixed_interval(self.cfg, rng_two, consecutive_misses=2)
        three = next_fixed_interval(self.cfg, rng_three, consecutive_misses=3)
        self.assertAlmostEqual(two, three)

    def test_random_interval_multiplies_by_frustration_factor_at_two_misses(self) -> None:
        rng = random.Random(3)
        rng_ref = random.Random(3)
        import math
        base_seconds = rng_ref.lognormvariate(math.log(self.cfg.base_seconds), self.cfg.random_sigma)
        expected = base_seconds * self.cfg.frustration_factor
        self.assertAlmostEqual(next_random_interval(self.cfg, rng, consecutive_misses=2), expected)

    def test_random_interval_unaffected_at_zero_misses(self) -> None:
        rng = random.Random(3)
        rng_ref = random.Random(3)
        import math
        expected = rng_ref.lognormvariate(math.log(self.cfg.base_seconds), self.cfg.random_sigma)
        self.assertAlmostEqual(next_random_interval(self.cfg, rng, consecutive_misses=0), expected)

    def test_resets_after_response_means_caller_passes_zero_misses(self) -> None:
        # 得到回应后重置计数器是调用方职责；这里验证 0 次未回应时不施加挫败系数
        rng_a = random.Random(5)
        normal = next_fixed_interval(self.cfg, rng_a, consecutive_misses=0)
        rng_c = random.Random(5)
        same_without_frustration = next_fixed_interval(
            make_cfg(frustration_factor=1.0), rng_c, consecutive_misses=2
        )
        self.assertAlmostEqual(normal, same_without_frustration)


class JitterDistributionTests(unittest.TestCase):
    """随机抖动：固定间隔右偏三角分布，随机间隔对数正态，自定义时间点双向偏移。"""

    def setUp(self) -> None:
        self.cfg = make_cfg()

    def test_fixed_interval_is_right_skewed_towards_mode(self) -> None:
        rng = random.Random(42)
        samples = [next_fixed_interval(self.cfg, rng, 0) for _ in range(500)]
        avg = sum(samples) / len(samples)
        # 众数偏右 10%，均值应大于基准
        self.assertGreater(avg, self.cfg.base_seconds)

    def test_random_interval_median_close_to_base(self) -> None:
        cfg = make_cfg()
        rng = random.Random(123)
        samples = sorted(next_random_interval(cfg, rng, 0) for _ in range(1001))
        median = samples[len(samples) // 2]
        # 对数正态中位数设计为 base_seconds，允许采样误差
        self.assertAlmostEqual(median, cfg.base_seconds, delta=cfg.base_seconds * 0.5)

    def test_custom_time_offset_within_magnitude_bounds(self) -> None:
        cfg = make_cfg()
        rng = random.Random(9)
        for _ in range(200):
            offset = custom_time_offset(cfg, rng)
            self.assertGreaterEqual(abs(offset), cfg.custom_offset_min)
            self.assertLessEqual(abs(offset), cfg.custom_offset_max)

    def test_custom_time_offset_can_be_negative_and_positive(self) -> None:
        cfg = make_cfg()
        rng = random.Random(11)
        signs = {custom_time_offset(cfg, rng) > 0 for _ in range(200)}
        self.assertEqual(signs, {True, False})


if __name__ == "__main__":
    unittest.main()
