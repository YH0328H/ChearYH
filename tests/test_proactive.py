"""Tests for proactive expression scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cether.proactive import (
    GateResult,
    ProactiveCandidate,
    ProactiveConfig,
    ProactiveScheduler,
    load_proactive_config,
)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Create a temporary proactive config file."""
    config_text = """
[scheduler]
check_interval = 300
global_cooldown = 1800
frequency_limit = 10

[triggers.idle]
enabled = true
threshold_seconds = 1800
cooldown = 3600
priority = 0.5

[triggers.stress]
enabled = true
keywords = ["bug", "error", "deadline"]
cooldown = 7200
priority = 0.8

[triggers.mindbox]
enabled = true
lookback_days = 14
cooldown = 86400
priority = 0.7

[triggers.weather]
enabled = false
cooldown = 43200
priority = 0.6

[gates]
require_awake = true
require_window_active = true
respect_silent_mode = true
"""
    path = tmp_path / "proactive.toml"
    path.write_text(config_text, encoding="utf-8")
    return path


def test_load_config(config_path: Path) -> None:
    """Config loads with expected defaults and custom values."""
    cfg = load_proactive_config(config_path)
    assert cfg.scheduler.check_interval == 300
    assert cfg.scheduler.global_cooldown == 1800
    assert cfg.idle.enabled is True
    assert cfg.idle.threshold_seconds == 1800
    assert cfg.stress.keywords == ("bug", "error", "deadline")
    assert cfg.weather.enabled is False
    assert cfg.gates.require_awake is True


def test_idle_trigger_fires_when_threshold_exceeded() -> None:
    """IdleTrigger produces a candidate when user has been idle long enough."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(seconds=2000)  # 33 minutes
    
    candidates = scheduler.evaluate_triggers({
        "last_interaction_ts": last_interaction,
    })
    
    assert len(candidates) == 1
    assert candidates[0].trigger_kind == "idle"
    assert candidates[0].reason == "user_idle"
    assert candidates[0].priority == 0.5


def test_idle_trigger_does_not_fire_below_threshold() -> None:
    """IdleTrigger produces no candidate when idle time is below threshold."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(seconds=1000)  # 16 minutes
    
    candidates = scheduler.evaluate_triggers({
        "last_interaction_ts": last_interaction,
    })
    
    assert not any(c.trigger_kind == "idle" for c in candidates)


def test_stress_trigger_fires_on_keyword_match() -> None:
    """StressTrigger produces a candidate when perception contains stress keywords."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    candidates = scheduler.evaluate_triggers({
        "perception": {"description": "User is debugging a bug in the error handler"}
    })
    
    stress_candidates = [c for c in candidates if c.trigger_kind == "stress"]
    assert len(stress_candidates) == 1
    assert stress_candidates[0].reason == "stress_detected"
    assert stress_candidates[0].priority == 0.8
    assert "bug" in stress_candidates[0].metadata["matched_keywords"]
    assert "error" in stress_candidates[0].metadata["matched_keywords"]


def test_stress_trigger_does_not_fire_without_keywords() -> None:
    """StressTrigger produces no candidate when perception has no stress keywords."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    candidates = scheduler.evaluate_triggers({
        "perception": {"description": "User is reading documentation"}
    })
    
    assert not any(c.trigger_kind == "stress" for c in candidates)


def test_mindbox_trigger_fires_for_old_concerns() -> None:
    """MindBoxTrigger produces a candidate when unresolved concerns exist in lookback window."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    old_concern_ts = now - timedelta(days=15)
    
    candidates = scheduler.evaluate_triggers({
        "mind_box": [
            {"ts": old_concern_ts, "topic": "project deadline", "resolved": False}
        ]
    })
    
    mindbox_candidates = [c for c in candidates if c.trigger_kind == "mindbox"]
    assert len(mindbox_candidates) == 1
    assert mindbox_candidates[0].reason == "mindbox_review"
    assert mindbox_candidates[0].topic == "project deadline"


def test_mindbox_trigger_ignores_resolved_concerns() -> None:
    """MindBoxTrigger ignores resolved concerns."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    old_concern_ts = now - timedelta(days=15)
    
    candidates = scheduler.evaluate_triggers({
        "mind_box": [
            {"ts": old_concern_ts, "topic": "project deadline", "resolved": True}
        ]
    })
    
    assert not any(c.trigger_kind == "mindbox" for c in candidates)


def test_gate_blocks_when_sleeping() -> None:
    """Awake gate blocks when role is sleeping."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    result = scheduler.check_gates({
        "perception": {"sleeping": True}
    })
    
    assert result.passed is False
    assert result.blocked_by == "sleeping"


def test_gate_blocks_on_window_checkpoint_reason() -> None:
    """Window gate blocks when checkpoint has a block reason."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    result = scheduler.check_gates({
        "window": {"checkpoint_block_reason": "hourly_cap"}
    })
    
    assert result.passed is False
    assert result.blocked_by == "hourly_cap"


def test_gate_blocks_in_silent_mode() -> None:
    """Silent mode gate blocks when mode is silent."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    result = scheduler.check_gates({"mode": "silent"})
    
    assert result.passed is False
    assert result.blocked_by == "silent_mode"


def test_gate_blocks_within_global_cooldown() -> None:
    """Global cooldown gate blocks when last proactive was too recent."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    
    # Simulate a recent proactive expression
    scheduler._last_proactive_ts = now - timedelta(seconds=1000)  # 16 minutes ago
    
    result = scheduler.check_gates({})
    
    assert result.passed is False
    assert result.blocked_by == "global_cooldown"


def test_gate_passes_after_global_cooldown() -> None:
    """Global cooldown gate passes when sufficient time has elapsed."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    
    scheduler._last_proactive_ts = now - timedelta(seconds=2000)  # 33 minutes ago
    
    result = scheduler.check_gates({})
    
    assert result.passed is True
    assert result.blocked_by is None


def test_frequency_limit_blocks_when_daily_cap_reached() -> None:
    """Frequency limit gate blocks when daily expression limit is reached."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    
    scheduler._daily_count = 10
    scheduler._daily_reset_date = now.date()
    
    result = scheduler.check_gates({})
    
    assert result.passed is False
    assert result.blocked_by == "frequency_limit"


def test_frequency_limit_resets_daily() -> None:
    """Frequency limit resets on a new day."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date()
    
    scheduler._daily_count = 10
    scheduler._daily_reset_date = yesterday
    
    result = scheduler.check_gates({})
    
    assert result.passed is True
    assert scheduler._daily_count == 0


def test_select_highest_priority_candidate() -> None:
    """Scheduler selects the highest-priority candidate when multiple pass gates."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    candidates = [
        ProactiveCandidate("idle", 0.5, "user_idle"),
        ProactiveCandidate("stress", 0.8, "stress_detected"),
        ProactiveCandidate("mindbox", 0.7, "mindbox_review"),
    ]
    
    selected = scheduler.select_candidate(candidates, {})
    
    assert selected is not None
    assert selected.trigger_kind == "stress"
    assert selected.priority == 0.8


def test_select_candidate_returns_none_when_gates_fail() -> None:
    """Scheduler returns None when all gates fail."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    
    candidates = [ProactiveCandidate("idle", 0.5, "user_idle")]
    
    selected = scheduler.select_candidate(candidates, {"mode": "silent"})
    
    assert selected is None


def test_record_expression_updates_state() -> None:
    """Recording an expression updates last_proactive_ts and daily count."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    candidate = ProactiveCandidate("idle", 0.5, "user_idle")
    
    scheduler.record_expression(candidate)
    
    assert scheduler._last_proactive_ts is not None
    assert scheduler._daily_count == 1
    assert scheduler._last_trigger_ts["idle"] is not None


def test_trigger_cooldown_prevents_repeat_firing() -> None:
    """Per-trigger cooldown prevents the same trigger from firing too soon."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(seconds=2000)
    
    # First evaluation produces idle candidate
    candidates1 = scheduler.evaluate_triggers({"last_interaction_ts": last_interaction})
    assert any(c.trigger_kind == "idle" for c in candidates1)
    
    # Record it
    idle_candidate = next(c for c in candidates1 if c.trigger_kind == "idle")
    scheduler.record_expression(idle_candidate)
    
    # Second evaluation should not produce idle candidate (still in cooldown)
    candidates2 = scheduler.evaluate_triggers({"last_interaction_ts": last_interaction})
    assert not any(c.trigger_kind == "idle" for c in candidates2)


def test_tick_integrates_evaluate_and_select() -> None:
    """tick() integrates trigger evaluation and candidate selection."""
    cfg = load_proactive_config(config_path := Path("config/proactive.toml"))
    scheduler = ProactiveScheduler(cfg)
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(seconds=2000)
    
    selected = scheduler.tick({
        "last_interaction_ts": last_interaction,
        "perception": {"description": "User found a bug"},
    })
    
    assert selected is not None
    assert selected.trigger_kind == "stress"  # Higher priority than idle
    assert selected.priority == 0.8
