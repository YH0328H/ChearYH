from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.cognition import (
    DecisionConfig, ExpressionConfig, LocalDecisionProvider,
    LocalExpressionProvider, load_cognition_config,
)


class CognitionTests(unittest.TestCase):
    def test_gate_sleep_impulse_and_battery_paths(self):
        decide = LocalDecisionProvider()
        self.assertFalse(decide.decide({"gate_reason": "quiet"}).speak)
        self.assertFalse(decide.decide({"state": {"expression_impulse": 0}}).speak)
        result = decide.decide({"state": {"social_battery": 0.1}})
        self.assertEqual(result.kind, "soft_refusal")
        self.assertTrue(result.speak)

    def test_expression_is_deterministic_and_uses_existing_description(self):
        provider = LocalExpressionProvider()
        decision = LocalDecisionProvider().decide({})
        request = {"context": type("Context", (), {"perception": {"description": "rain outside"}})(),
                   "state": {"social_battery": 0.8}}
        self.assertEqual(provider.express(decision, request).text, "rain outside")
        self.assertEqual(provider.express(decision, request), provider.express(decision, request))

    def test_toml_and_threshold_validation(self):
        decision, expression = load_cognition_config(ROOT / "config" / "cognition.toml")
        self.assertEqual(decision.low_battery_threshold, 0.2)
        self.assertEqual(expression.full_battery_threshold, 0.35)
        with self.assertRaises(ValueError):
            DecisionConfig(low_impulse_threshold=2)
        with self.assertRaises(ValueError):
            ExpressionConfig(full_battery_threshold=-1)


if __name__ == "__main__":
    unittest.main()
