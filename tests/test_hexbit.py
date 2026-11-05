import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.hexbit import (  # noqa: E402
    DIMENSION_NAMES,
    EncodedResult,
    HexbitConfig,
    apply_hexbit_penalty,
    default_dimension_fns,
    encode_six_bits,
)


class EncodeSixBitsTests(unittest.TestCase):
    def test_all_dimensions_false_gives_zero(self) -> None:
        code = encode_six_bits({})
        self.assertEqual(code, 0)

    def test_all_dimensions_true_gives_sixty_three(self) -> None:
        features = {
            "valence": 0.5,
            "salience": 0.9,
            "emotion": 0.9,
            "relation_event": True,
            "self_initiated": True,
            "flash_weight": True,
        }
        code = encode_six_bits(features)
        self.assertEqual(code, 0b111111)

    def test_single_dimension_sets_correct_bit(self) -> None:
        # valence_positive 是 bit 0
        code = encode_six_bits({"valence": 0.3})
        self.assertEqual(code, 1)

    def test_no_random_hash_same_input_gives_same_code(self) -> None:
        features = {"valence": 0.2, "salience": 0.8, "salience_threshold": 0.7}
        codes = {encode_six_bits(features) for _ in range(20)}
        self.assertEqual(len(codes), 1)  # 禁止随机哈希：同输入必须恒定输出

    def test_dimension_names_has_six_entries(self) -> None:
        self.assertEqual(len(DIMENSION_NAMES), 6)

    def test_custom_dimension_fns_override_defaults(self) -> None:
        custom = default_dimension_fns()
        custom["valence_positive"] = lambda f: True  # 强制该维度始终为真
        code = encode_six_bits({}, dimension_fns=custom)
        self.assertEqual(code & 1, 1)


class ApplyHexbitPenaltyTests(unittest.TestCase):
    def test_empty_list_returns_empty(self) -> None:
        self.assertEqual(apply_hexbit_penalty([]), [])

    def test_single_result_no_penalty(self) -> None:
        results = [EncodedResult("a", 1.0, code=5)]
        adjusted = apply_hexbit_penalty(results)
        self.assertEqual(adjusted[0].score, 1.0)

    def test_different_codes_no_penalty(self) -> None:
        results = [EncodedResult("a", 1.0, code=1), EncodedResult("b", 1.0, code=2)]
        adjusted = apply_hexbit_penalty(results)
        self.assertEqual(adjusted[0].score, 1.0)
        self.assertEqual(adjusted[1].score, 1.0)

    def test_consecutive_same_code_applies_decreasing_penalty(self) -> None:
        cfg = HexbitConfig(decay_factor=0.8, min_repeat_to_penalize=1)
        results = [
            EncodedResult("a", 1.0, code=7),
            EncodedResult("b", 1.0, code=7),
            EncodedResult("c", 1.0, code=7),
        ]
        adjusted = apply_hexbit_penalty(results, cfg)
        self.assertEqual(adjusted[0].score, 1.0)  # 第一次命中不计重复
        self.assertAlmostEqual(adjusted[1].score, 1.0 * 0.8**1)
        self.assertAlmostEqual(adjusted[2].score, 1.0 * 0.8**2)

    def test_code_change_resets_repeat_count(self) -> None:
        cfg = HexbitConfig(decay_factor=0.8, min_repeat_to_penalize=1)
        results = [
            EncodedResult("a", 1.0, code=7),
            EncodedResult("b", 1.0, code=7),
            EncodedResult("c", 1.0, code=9),  # 编码变化，重置计数
            EncodedResult("d", 1.0, code=9),
        ]
        adjusted = apply_hexbit_penalty(results, cfg)
        self.assertAlmostEqual(adjusted[1].score, 1.0 * 0.8**1)
        self.assertEqual(adjusted[2].score, 1.0)  # 编码切换，第一次命中不罚
        self.assertAlmostEqual(adjusted[3].score, 1.0 * 0.8**1)

    def test_min_repeat_to_penalize_delays_first_penalty(self) -> None:
        cfg = HexbitConfig(decay_factor=0.5, min_repeat_to_penalize=2)
        results = [
            EncodedResult("a", 1.0, code=1),
            EncodedResult("b", 1.0, code=1),
            EncodedResult("c", 1.0, code=1),
        ]
        adjusted = apply_hexbit_penalty(results, cfg)
        self.assertEqual(adjusted[0].score, 1.0)
        self.assertEqual(adjusted[1].score, 1.0)  # repeat_count=1 < threshold 2
        self.assertAlmostEqual(adjusted[2].score, 1.0 * 0.5**2)  # repeat_count=2 >= threshold

    def test_order_preserved(self) -> None:
        results = [EncodedResult("a", 1.0, code=1), EncodedResult("b", 2.0, code=1)]
        adjusted = apply_hexbit_penalty(results)
        self.assertEqual([r.doc_id for r in adjusted], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
