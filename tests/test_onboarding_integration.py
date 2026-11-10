"""Integration tests for onboarding flow."""

import pytest
import json
from pathlib import Path
from cether.desktop import DesktopRuntime


@pytest.fixture
def runtime_for_onboarding(tmp_path: Path) -> DesktopRuntime:
    """Create a runtime for onboarding testing."""
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
    
    runtime = DesktopRuntime(data_dir=data_dir)
    
    return runtime


def test_bootstrap_returns_onboarding_modules(runtime_for_onboarding: DesktopRuntime) -> None:
    """bootstrap action returns onboarding module list."""
    result = runtime_for_onboarding.handle({"action": "bootstrap"})
    
    assert "onboarding" in result
    assert "modules" in result["onboarding"]
    
    modules = result["onboarding"]["modules"]
    assert len(modules) >= 6  # At least 6 default modules
    
    # Check first module structure
    if modules:
        first = modules[0]
        assert "id" in first or "name" in first


def test_bootstrap_onboarding_not_completed_initially(runtime_for_onboarding: DesktopRuntime) -> None:
    """Onboarding is not completed initially."""
    result = runtime_for_onboarding.handle({"action": "bootstrap"})
    
    assert result["onboarding"]["completed"] is False


def test_complete_onboarding_marks_as_done(runtime_for_onboarding: DesktopRuntime) -> None:
    """complete_onboarding marks onboarding as completed."""
    result = runtime_for_onboarding.handle({
        "action": "complete_onboarding",
        "preferences": {},
    })
    
    assert result["success"] is True
    
    # Check it's marked in bootstrap
    bootstrap = runtime_for_onboarding.handle({"action": "bootstrap"})
    assert bootstrap["onboarding"]["completed"] is True


def test_complete_onboarding_saves_local_fallback_preference(runtime_for_onboarding: DesktopRuntime) -> None:
    """complete_onboarding saves local_fallback preference."""
    result = runtime_for_onboarding.handle({
        "action": "complete_onboarding",
        "preferences": {
            "local_fallback": True,
        },
    })
    
    assert result["success"] is True
    
    # Check preference is saved
    onboarding_path = runtime_for_onboarding.data_dir / "onboarding.json"
    assert onboarding_path.exists()
    
    state = json.loads(onboarding_path.read_text(encoding="utf-8"))
    assert state["completed"] is True
    assert state["local_fallback"] is True
    assert "completed_at" in state


def test_complete_onboarding_without_preferences(runtime_for_onboarding: DesktopRuntime) -> None:
    """complete_onboarding works without preferences."""
    result = runtime_for_onboarding.handle({
        "action": "complete_onboarding",
    })
    
    assert result["success"] is True
    
    onboarding_path = runtime_for_onboarding.data_dir / "onboarding.json"
    state = json.loads(onboarding_path.read_text(encoding="utf-8"))
    assert state["completed"] is True
