"""Gate for proactive expression: quiet hours, busy, presence, daily cap, cooldown.

`check` is pure. It returns the first failing reason, so the caller can log
it and skip the model call. Passing returns `None`.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path


@dataclass(frozen=True)
class GateConfig:
    quiet_start: time
    quiet_end: time
    daily_cap: int
    cooldown_seconds: int


@dataclass(frozen=True)
class GateState:
    now: datetime
    busy: bool
    present: bool
    sent_today: int
    last_sent_at: datetime | None


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def load_gate_config(path: Path) -> GateConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = GateConfig(
        quiet_start=_parse_hhmm(raw["quiet"]["start"]),
        quiet_end=_parse_hhmm(raw["quiet"]["end"]),
        daily_cap=int(raw["expression"]["daily_cap"]),
        cooldown_seconds=int(raw["expression"]["cooldown_seconds"]),
    )
    if cfg.daily_cap < 0 or cfg.cooldown_seconds < 0:
        raise ValueError("daily_cap and cooldown_seconds must be >= 0")
    return cfg


def in_quiet_hours(t: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= t < end
    # 跨午夜，例如 23:00 - 07:00
    return t >= start or t < end


def check(cfg: GateConfig, state: GateState) -> str | None:
    """Return the first blocking reason, or None if expression may proceed."""
    if in_quiet_hours(state.now.time(), cfg.quiet_start, cfg.quiet_end):
        return "quiet_hours"
    if state.busy:
        return "busy"
    if not state.present:
        return "not_present"
    if state.sent_today >= cfg.daily_cap:
        return "daily_cap_reached"
    if state.last_sent_at is not None:
        elapsed = (state.now - state.last_sent_at).total_seconds()
        if elapsed < cfg.cooldown_seconds:
            return "cooldown"
    return None
