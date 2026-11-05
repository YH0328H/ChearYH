import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.state import (  # noqa: E402
    FourWill,
    SixDrives,
    TensionStateConfig,
    compute_surprise,
    detect_tension_state,
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


class TensionStateTests(unittest.TestCase):
    """张力态自然涌现（TASK.md 60/227）：至少覆盖四种张力态，可观测、可复算。"""

    def setUp(self) -> None:
        self.cfg = TensionStateConfig()

    def test_close_but_afraid_triggers_on_high_connection_low_security(self) -> None:
        will = FourWill(social_battery=0.6, connection_desire=0.8, expression_impulse=0.5, security=0.3)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        names = {h.name for h in hits}
        self.assertIn("想靠近但不敢", names)

    def test_tired_but_reluctant_triggers_on_low_battery_high_connection(self) -> None:
        will = FourWill(social_battery=0.2, connection_desire=0.7, expression_impulse=0.5, security=0.6)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        names = {h.name for h in hits}
        self.assertIn("累了但舍不得走", names)

    def test_afraid_to_speak_triggers_on_high_impulse_low_security(self) -> None:
        will = FourWill(social_battery=0.6, connection_desire=0.3, expression_impulse=0.7, security=0.3)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        names = {h.name for h in hits}
        self.assertIn("想说话但怕说错", names)

    def test_disappointed_triggers_on_high_impulse_low_valence(self) -> None:
        will = FourWill(social_battery=0.6, connection_desire=0.3, expression_impulse=0.7, security=0.6)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=-0.5, config=self.cfg)
        names = {h.name for h in hits}
        self.assertIn("期待但失望", names)

    def test_no_hits_when_all_moderate(self) -> None:
        will = FourWill(social_battery=0.5, connection_desire=0.5, expression_impulse=0.5, security=0.5)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        self.assertEqual(hits, [])

    def test_evidence_contains_the_triggering_values(self) -> None:
        will = FourWill(social_battery=0.6, connection_desire=0.8, expression_impulse=0.5, security=0.3)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        hit = next(h for h in hits if h.name == "想靠近但不敢")
        self.assertAlmostEqual(hit.evidence["connection_desire"], 0.8)
        self.assertAlmostEqual(hit.evidence["security"], 0.3)
        self.assertAlmostEqual(hit.evidence["relation_tension"], 0.5)

    def test_multiple_tension_states_can_coexist(self) -> None:
        # 连接渴望高+安全感低 同时 社交电量低 → 想靠近但不敢 + 累了但舍不得走 同时触发
        will = FourWill(social_battery=0.2, connection_desire=0.8, expression_impulse=0.5, security=0.3)
        hits = detect_tension_state(will, relation_tension=0.5, momentary_valence=0.0, config=self.cfg)
        names = {h.name for h in hits}
        self.assertEqual(names, {"想靠近但不敢", "累了但舍不得走"})

    def test_full_derivation_close_but_afraid_from_six_drives(self) -> None:
        """TASK.md 227：六维驱力初值 → 惯性滤波 → 四意愿终值 → 张力态，全程可复算。

        场景：角色刚经历一次让她有点失望的互动（certainty 走低、seeking 走高），
        但又很想维系关系（affiliation 高、care 高）。
        """
        # 六维驱力初值（上一拍状态）
        drives_prev = SixDrives(seeking=0.5, affiliation=0.5, competence=0.5, certainty=0.6, care=0.5, play=0.5)
        # 六维驱力目标值（本拍感知后的瞬时目标）
        drives_target = SixDrives(seeking=0.7, affiliation=0.9, competence=0.5, certainty=0.2, care=0.8, play=0.3)

        alpha = 0.7
        drives_filtered = SixDrives(
            seeking=inertial_filter(drives_prev.seeking, drives_target.seeking, alpha),
            affiliation=inertial_filter(drives_prev.affiliation, drives_target.affiliation, alpha),
            competence=inertial_filter(drives_prev.competence, drives_target.competence, alpha),
            certainty=inertial_filter(drives_prev.certainty, drives_target.certainty, alpha),
            care=inertial_filter(drives_prev.care, drives_target.care, alpha),
            play=inertial_filter(drives_prev.play, drives_target.play, alpha),
        )
        # 手工复算惯性滤波：v = 0.7*current + 0.3*target
        self.assertAlmostEqual(drives_filtered.seeking, 0.7 * 0.5 + 0.3 * 0.7, places=6)       # 0.56
        self.assertAlmostEqual(drives_filtered.affiliation, 0.7 * 0.5 + 0.3 * 0.9, places=6)   # 0.62
        self.assertAlmostEqual(drives_filtered.certainty, 0.7 * 0.6 + 0.3 * 0.2, places=6)     # 0.48
        self.assertAlmostEqual(drives_filtered.care, 0.7 * 0.5 + 0.3 * 0.8, places=6)          # 0.59

        will = project_six_drives_to_four_will(drives_filtered, social_battery_current=0.6)
        # 手工复算四意愿：
        # connection_desire = affiliation*0.7 + care*0.3 = 0.62*0.7 + 0.59*0.3 = 0.434+0.177=0.611
        self.assertAlmostEqual(will.connection_desire, 0.62 * 0.7 + 0.59 * 0.3, places=6)
        # security = certainty*0.8 - seeking*0.2 = 0.48*0.8 - 0.56*0.2 = 0.384-0.112=0.272
        self.assertAlmostEqual(will.security, 0.48 * 0.8 - 0.56 * 0.2, places=6)

        cfg = TensionStateConfig()
        hits = detect_tension_state(will, relation_tension=0.6, momentary_valence=-0.1, config=cfg)
        names = {h.name for h in hits}
        # connection_desire≈0.611≥0.7? 否，低于默认阈值0.7 —— 用更敏感阈值验证区间判定的连续性
        self.assertNotIn("想靠近但不敢", names)
        sensitive_cfg = TensionStateConfig(close_but_afraid_connection_min=0.6, close_but_afraid_security_max=0.3)
        hits_sensitive = detect_tension_state(will, relation_tension=0.6, momentary_valence=-0.1, config=sensitive_cfg)
        self.assertIn("想靠近但不敢", {h.name for h in hits_sensitive})

    def test_full_derivation_tired_but_reluctant_from_six_drives(self) -> None:
        """TASK.md 227：第二个指定张力态"累了但舍不得走"的全程可复算推演。"""
        drives_prev = SixDrives(seeking=0.5, affiliation=0.5, competence=0.5, certainty=0.5, care=0.5, play=0.5)
        drives_target = SixDrives(seeking=0.3, affiliation=0.9, competence=0.4, certainty=0.5, care=0.85, play=0.2)
        alpha = 0.7
        affiliation_filtered = inertial_filter(drives_prev.affiliation, drives_target.affiliation, alpha)
        care_filtered = inertial_filter(drives_prev.care, drives_target.care, alpha)
        self.assertAlmostEqual(affiliation_filtered, 0.7 * 0.5 + 0.3 * 0.9, places=6)  # 0.62
        self.assertAlmostEqual(care_filtered, 0.7 * 0.5 + 0.3 * 0.85, places=6)         # 0.605

        drives_filtered = SixDrives(
            seeking=inertial_filter(drives_prev.seeking, drives_target.seeking, alpha),
            affiliation=affiliation_filtered,
            competence=inertial_filter(drives_prev.competence, drives_target.competence, alpha),
            certainty=inertial_filter(drives_prev.certainty, drives_target.certainty, alpha),
            care=care_filtered,
            play=inertial_filter(drives_prev.play, drives_target.play, alpha),
        )
        # 社交电量独立维护：本拍因长时间陪伴已耗到 0.25（快变层，不经惯性滤波，直接传入）
        will = project_six_drives_to_four_will(drives_filtered, social_battery_current=0.25)
        connection_desire_expected = affiliation_filtered * 0.7 + care_filtered * 0.3
        self.assertAlmostEqual(will.connection_desire, connection_desire_expected, places=6)  # ≈0.615

        cfg = TensionStateConfig()
        hits = detect_tension_state(will, relation_tension=0.4, momentary_valence=0.1, config=cfg)
        names = {h.name for h in hits}
        self.assertIn("累了但舍不得走", names)
        hit = next(h for h in hits if h.name == "累了但舍不得走")
        self.assertAlmostEqual(hit.evidence["social_battery"], 0.25)
        self.assertAlmostEqual(hit.evidence["connection_desire"], connection_desire_expected, places=6)


if __name__ == "__main__":
    unittest.main()
