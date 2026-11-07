"""Deterministic schedule and idle policy for role-local sleep modes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Callable
import tomllib


def _parse_time(value: str) -> time:
    try:
        hour, minute = (int(item) for item in value.split(":", 1))
        return time(hour, minute)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid sleep schedule time: {value!r}") from exc


@dataclass(frozen=True)
class SleepScheduleConfig:
    enabled: bool = False
    light_start: str = "22:00"
    light_end: str = "23:00"
    deep_start: str = "23:00"
    deep_end: str = "07:00"
    idle_seconds: float = 900.0

    def __post_init__(self) -> None:
        if self.idle_seconds < 0:
            raise ValueError("idle_seconds must be non-negative")
        for value in (self.light_start, self.light_end, self.deep_start, self.deep_end):
            _parse_time(value)


def load_sleep_schedule_config(path: Path) -> SleepScheduleConfig:
    """Load the optional schedule section from TOML."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return SleepScheduleConfig(**raw.get("sleep_schedule", {}))


class SleepSchedule:
    """Return awake/light/deep from local clock windows and user idle time."""

    def __init__(self, config: SleepScheduleConfig = SleepScheduleConfig(), *, last_activity: Callable[[], datetime] | None = None) -> None:
        self.config = config
        self._last_activity = last_activity
        self._last_user_activity: datetime | None = None

    def mark_activity(self, at: datetime) -> None:
        self._last_user_activity = at

    def __call__(self, now: datetime) -> str:
        if not self.config.enabled:
            return "awake"
        activity = self._last_activity() if self._last_activity else self._last_user_activity
        if activity is not None and (now - activity).total_seconds() < self.config.idle_seconds:
            return "awake"
        minute = now.hour * 60 + now.minute
        if _in_window(minute, _minutes(self.config.light_start), _minutes(self.config.light_end)):
            return "light"
        if _in_window(minute, _minutes(self.config.deep_start), _minutes(self.config.deep_end)):
            return "deep"
        return "awake"


def _minutes(value: str) -> int:
    parsed = _parse_time(value)
    return parsed.hour * 60 + parsed.minute


def _in_window(current: int, start: int, end: int) -> bool:
    if start == end:
        return False
    return start <= current < end if start < end else current >= start or current < end
