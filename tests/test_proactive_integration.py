"""Integration tests for proactive expression in desktop runtime."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cether.desktop import DesktopRuntime


@pytest.fixture
def runtime_with_proactive(tmp_path: Path) -> DesktopRuntime:
    """Create a desktop runtime with proactive config."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # Create config directory
    config_dir = data_dir / "config"
    config_dir.mkdir()
    
    # Create minimal configs
    (config_dir / "chat.toml").write_text(
        '[chat]\nbase_url = "http://localhost:11434"\nmodel_id = "test"\nkey_env = "TEST_KEY"',
        encoding="utf-8"
    )
    (config_dir / "cognition.toml").write_text(
        '[decision]\n[expression]',
        encoding="utf-8"
    )
    (config_dir / "proactive.toml").write_text("""
[scheduler]
check_interval = 60
global_cooldown = 300
frequency_limit = 10

[triggers.idle]
enabled = true
threshold_seconds = 600
cooldown = 1200
priority = 0.5

[triggers.stress]
enabled = true
keywords = ["bug", "error"]
cooldown = 3600
priority = 0.8

[triggers.mindbox]
enabled = false
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
""", encoding="utf-8")
    
    runtime = DesktopRuntime(data_dir=data_dir)
    
    # Bootstrap with a test role
    runtime.handle({"action": "bootstrap"})
    runtime.handle({
        "action": "create_role",
        "name": "ProactiveTest",
        "persona": {"name": "Test", "traits": []},
    })
    
    return runtime


def test_check_proactive_returns_none_when_no_triggers_fire(runtime_with_proactive: DesktopRuntime) -> None:
    """check_proactive returns None when no triggers are ready."""
    result = runtime_with_proactive.handle({
        "action": "check_proactive",
        "perception": {"description": "User is working"},
    })
    
    assert result["candidate"] is None


def test_check_proactive_returns_idle_candidate_after_threshold(runtime_with_proactive: DesktopRuntime) -> None:
    """check_proactive returns idle candidate when user has been idle long enough."""
    # Mock last interaction timestamp
    role_name = runtime_with_proactive.registry.active.config.role_id
    if not role_name:
        pytest.skip("No active role")
    
    if not runtime_with_proactive.runtime:
        pytest.skip("Runtime not ready")
    
    now = datetime.now(timezone.utc)
    state = runtime_with_proactive.runtime._read_state()
    state["last_interaction_ts"] = now - timedelta(seconds=700)
    runtime_with_proactive.runtime._state = state  # 11 minutes
    
    result = runtime_with_proactive.handle({
        "action": "check_proactive",
        "perception": {},
    })
    
    assert result["candidate"] is not None
    assert result["candidate"]["trigger_kind"] == "idle"
    assert result["candidate"]["reason"] == "user_idle"


def test_check_proactive_returns_stress_candidate_on_keyword(runtime_with_proactive: DesktopRuntime) -> None:
    """check_proactive returns stress candidate when perception contains stress keywords."""
    result = runtime_with_proactive.handle({
        "action": "check_proactive",
        "perception": {"description": "Found a critical bug in the error handler"},
    })
    
    assert result["candidate"] is not None
    assert result["candidate"]["trigger_kind"] == "stress"
    assert result["candidate"]["priority"] == 0.8


def test_check_proactive_respects_gates(runtime_with_proactive: DesktopRuntime) -> None:
    """check_proactive respects gates and blocks when sleeping."""
    role_name = runtime_with_proactive.registry.active.config.role_id
    if not role_name:
        pytest.skip("No active role")
    
    if not runtime_with_proactive.runtime:
        pytest.skip("Runtime not ready")
    
    
    now = datetime.now(timezone.utc)
    state = runtime_with_proactive.runtime._read_state()
    state["last_interaction_ts"] = now - timedelta(seconds=700)
    runtime_with_proactive.runtime._state = state
    
    result = runtime_with_proactive.handle({
        "action": "check_proactive",
        "perception": {"sleeping": True},
    })
    
    assert result["candidate"] is None


def test_send_proactive_generates_expression(runtime_with_proactive: DesktopRuntime) -> None:
    """send_proactive generates and records an expression."""
    candidate_data = {
        "trigger_kind": "idle",
        "priority": 0.5,
        "reason": "user_idle",
        "topic": None,
        "metadata": {"idle_seconds": 700},
    }
    
    result = runtime_with_proactive.handle({
        "action": "send_proactive",
        "candidate": candidate_data,
        "presentation": "popup",
    })
    
    assert result["success"] is True
    assert "expression" in result
    assert result["expression"]["text"]
    assert result["expression"]["kind"] == "proactive"


def test_send_proactive_records_event(runtime_with_proactive: DesktopRuntime) -> None:
    """send_proactive writes an event to the role's event log."""
    candidate_data = {
        "trigger_kind": "stress",
        "priority": 0.8,
        "reason": "stress_detected",
        "topic": None,
        "metadata": {"matched_keywords": ["bug"]},
    }
    
    result = runtime_with_proactive.handle({
        "action": "send_proactive",
        "candidate": candidate_data,
    })
    
    assert result["success"] is True
    
    # Check event log
    role_name = runtime_with_proactive.registry.active.config.role_id
    if not role_name:
        pytest.skip("No active role")
    
    if not runtime_with_proactive.runtime:
        pytest.skip("Runtime not ready")
    
    
    events = runtime_with_proactive._events.subscribe(cursor=0, limit=10) if runtime_with_proactive._events else []
    
    proactive_events = [e for e in events["events"] if e["kind"] == "proactive_expression"]
    assert len(proactive_events) == 1
    assert proactive_events[0]["metadata"]["trigger"] == "stress"


def test_proactive_cooldown_prevents_rapid_fire(runtime_with_proactive: DesktopRuntime) -> None:
    """Proactive expressions respect global cooldown."""
    # First expression
    candidate_data = {
        "trigger_kind": "idle",
        "priority": 0.5,
        "reason": "user_idle",
    }
    
    result1 = runtime_with_proactive.handle({
        "action": "send_proactive",
        "candidate": candidate_data,
    })
    assert result1["success"] is True
    
    # Immediate second check should fail gates
    role_name = runtime_with_proactive.registry.active.config.role_id
    if not role_name:
        pytest.skip("No active role")
    
    if not runtime_with_proactive.runtime:
        pytest.skip("Runtime not ready")
    
    
    state = runtime_with_proactive.runtime._read_state()
    state["last_interaction_ts"] = datetime.now(timezone.utc) - timedelta(seconds=700)
    runtime_with_proactive.runtime._state = state
    
    result2 = runtime_with_proactive.handle({
        "action": "check_proactive",
        "perception": {},
    })
    
    assert result2["candidate"] is None  # Blocked by global cooldown
