from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.sleep_schedule import SleepSchedule, SleepScheduleConfig


def test_disabled_schedule_stays_awake() -> None:
    schedule = SleepSchedule(SleepScheduleConfig(enabled=False))
    assert schedule(datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)) == "awake"


def test_cross_midnight_deep_window_and_idle_threshold() -> None:
    config = SleepScheduleConfig(enabled=True, idle_seconds=60)
    schedule = SleepSchedule(config)
    schedule.mark_activity(datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc))
    assert schedule(datetime(2026, 1, 1, 23, 30, 30, tzinfo=timezone.utc)) == "awake"
    assert schedule(datetime(2026, 1, 2, 1, 0, tzinfo=timezone.utc)) == "deep"


def test_light_window_and_invalid_configuration() -> None:
    config = SleepScheduleConfig(enabled=True, light_start="20:00", light_end="21:00", deep_start="21:00", deep_end="06:00", idle_seconds=0)
    schedule = SleepSchedule(config)
    assert schedule(datetime(2026, 1, 1, 20, 30, tzinfo=timezone.utc)) == "light"
    with pytest.raises(ValueError):
        SleepScheduleConfig(light_start="bad")
