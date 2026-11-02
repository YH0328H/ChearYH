import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.trigger import EventContext, TriggerConfig, should_trigger_l1  # noqa: E402

NOW = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
CFG = TriggerConfig(emotion_high_threshold=0.7, salience_high_threshold=0.7, repetition_window_seconds=3600)


class TriggerTests(unittest.TestCase):
    def test_manual_mark_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=True, is_relation_event=False, emotion_intensity=0.0,
                           salience=0.0, theme=None)
        self.assertTrue(should_trigger_l1(ctx, CFG, []))

    def test_relation_event_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=True, emotion_intensity=0.0,
                           salience=0.0, theme=None)
        self.assertTrue(should_trigger_l1(ctx, CFG, []))

    def test_high_emotion_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.75,
                           salience=0.0, theme=None)
        self.assertTrue(should_trigger_l1(ctx, CFG, []))

    def test_high_salience_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.0,
                           salience=0.8, theme=None)
        self.assertTrue(should_trigger_l1(ctx, CFG, []))

    def test_repetition_within_window_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.0,
                           salience=0.0, theme="工作")
        recent = [(NOW - timedelta(minutes=30), "工作")]
        self.assertTrue(should_trigger_l1(ctx, CFG, recent))

    def test_repetition_outside_window_does_not_trigger(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.0,
                           salience=0.0, theme="工作")
        recent = [(NOW - timedelta(hours=2), "工作")]
        self.assertFalse(should_trigger_l1(ctx, CFG, recent))

    def test_no_trigger_when_all_low(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.3,
                           salience=0.4, theme="其他")
        self.assertFalse(should_trigger_l1(ctx, CFG, []))

    def test_emotion_at_threshold_triggers(self) -> None:
        ctx = EventContext(NOW, manual_mark=False, is_relation_event=False, emotion_intensity=0.7,
                           salience=0.0, theme=None)
        self.assertTrue(should_trigger_l1(ctx, CFG, []))


if __name__ == "__main__":
    unittest.main()
