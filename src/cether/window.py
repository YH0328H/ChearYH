"""Proactive windows and checkpoints.

Priority is sleep > silent mode > window > checkpoint. Checkpoints only run
inside a window. Overlapping windows merge: the stronger mode wins, and the
hourly cap is global. Randomness comes from an injected `random.Random` so
tests can fix the seed.
"""

from __future__ import annotations

import math
import random
import tomllib
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

MODE_RANK = {"allow": 1, "boost": 2}


@dataclass(frozen=True)
class Window:
    name: str
    start: time
    end: time
    mode: str
    penetrate: bool


@dataclass(frozen=True)
class CheckpointConfig:
    base_seconds: float
    hourly_cap: int
    frustration_factor: float
    skew_low: float
    skew_high: float
    skew_mode: float
    random_sigma: float
    custom_offset_min: float
    custom_offset_max: float


def _hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def load_window_config(path: Path) -> tuple[CheckpointConfig, list[Window]]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    c = raw["checkpoint"]
    cfg = CheckpointConfig(
        base_seconds=float(c["base_minutes"]) * 60,
        hourly_cap=int(c["hourly_cap"]),
        frustration_factor=float(c["frustration_factor"]),
        skew_low=float(c["fixed_skew_low"]),
        skew_high=float(c["fixed_skew_high"]),
        skew_mode=float(c["fixed_skew_mode"]),
        random_sigma=float(c["random_sigma"]),
        custom_offset_min=float(c["custom_offset_min_seconds"]),
        custom_offset_max=float(c["custom_offset_max_seconds"]),
    )
    if not cfg.skew_low <= cfg.skew_mode <= cfg.skew_high:
        raise ValueError("fixed skew mode must lie within [low, high]")
    windows = [
        Window(w["name"], _hhmm(w["start"]), _hhmm(w["end"]), w["mode"], bool(w["penetrate"]))
        for w in raw.get("window", [])
    ]
    for w in windows:
        if w.mode not in MODE_RANK:
            raise ValueError(f"{w.name}: unknown mode {w.mode!r}")
    return cfg, windows


def _in_range(t: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def active_mode(now: datetime, windows: list[Window]) -> str | None:
    """Return the strongest mode of all windows containing `now`, or None."""
    modes = [w.mode for w in windows if _in_range(now.time(), w.start, w.end)]
    return max(modes, key=MODE_RANK.get) if modes else None


def checkpoint_block_reason(
    now: datetime,
    windows: list[Window],
    sleeping: bool,
    silent_mode: bool,
    hourly_fires: list[datetime],
    hourly_cap: int,
) -> str | None:
    """Return why a checkpoint may not run now, or None if it may run."""
    if sleeping:
        return "sleeping"
    if silent_mode:
        return "silent_mode"
    if active_mode(now, windows) is None:
        return "outside_window"
    recent = [t for t in hourly_fires if now - t < timedelta(hours=1)]
    if len(recent) >= hourly_cap:
        return "hourly_cap"
    return None


def next_fixed_interval(cfg: CheckpointConfig, rng: random.Random, consecutive_misses: int) -> float:
    skew = rng.triangular(cfg.skew_low, cfg.skew_high, cfg.skew_mode)
    return _frustrated(cfg.base_seconds * (1 + skew), cfg, consecutive_misses)


def next_random_interval(cfg: CheckpointConfig, rng: random.Random, consecutive_misses: int) -> float:
    # 对数正态中位数为 base：mu = ln(base)
    seconds = rng.lognormvariate(math.log(cfg.base_seconds), cfg.random_sigma)
    return _frustrated(seconds, cfg, consecutive_misses)


def custom_time_offset(cfg: CheckpointConfig, rng: random.Random) -> float:
    magnitude = rng.uniform(cfg.custom_offset_min, cfg.custom_offset_max)
    return magnitude if rng.random() < 0.5 else -magnitude


def _frustrated(seconds: float, cfg: CheckpointConfig, consecutive_misses: int) -> float:
    # 连续两次未开口，间隔后移 50%；每多一次不再叠加
    return seconds * cfg.frustration_factor if consecutive_misses >= 2 else seconds
