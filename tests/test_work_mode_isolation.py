"""Tests for work mode memory isolation."""

import pytest
from pathlib import Path
from cether.desktop import DesktopRuntime


@pytest.fixture
def runtime_for_mode_test(tmp_path: Path) -> DesktopRuntime:
    """Create a runtime for mode testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
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


def test_companion_mode_writes_memory(runtime_for_mode_test: DesktopRuntime) -> None:
    """Companion mode writes conversation to memory."""
    # Bootstrap to initialize conversation
    runtime_for_mode_test.handle({"action": "bootstrap"})
    
    # Send in companion mode (default)
    result = runtime_for_mode_test.handle({
        "action": "send_message",
        "text": "测试陪伴模式记忆",
    })
    
    assert "turn" in result
    assert "history" in result
    
    # Verify the message appears in history (indicating it was persisted)
    history = result["history"]
    assert len(history) >= 2  # At least user + assistant
    
    # Check user message is in history
    user_messages = [turn for turn in history if turn.get("role") == "user"]
    assert any("测试陪伴模式记忆" in turn.get("text", "") for turn in user_messages)



def test_work_mode_skips_memory(runtime_for_mode_test: DesktopRuntime) -> None:
    """Work mode does not write conversation to memory."""
    # Bootstrap to initialize
    runtime_for_mode_test.handle({"action": "bootstrap"})
    
    # Override to work mode
    runtime_for_mode_test.handle({
        "action": "set_mode",
        "mode": "work",
    })
    
    # Send in work mode
    result = runtime_for_mode_test.handle({
        "action": "send_message",
        "text": "测试工作模式隔离",
    })
    
    assert "turn" in result
    
    # Check memory directory
    conversations_dir = runtime_for_mode_test.data_dir / "roles" / "default" / "conversations"
    
    if conversations_dir.exists():
        conv_files = list(conversations_dir.glob("*.jsonl"))
        if conv_files:
            # Read all conversations
            all_content = ""
            for f in conv_files:
                all_content += f.read_text(encoding="utf-8")
            
            # Work mode message should NOT be in memory
            assert "测试工作模式隔离" not in all_content
        else:
            # No conversation files - that's correct for work mode
            pass
    else:
        # No conversations directory - that's also correct
        pass


def test_mode_switch_affects_memory_persistence(runtime_for_mode_test: DesktopRuntime) -> None:
    """Switching modes affects whether memory is persisted."""
    runtime_for_mode_test.handle({"action": "bootstrap"})
    
    # First message in companion mode
    result1 = runtime_for_mode_test.handle({
        "action": "send_message",
        "text": "陪伴模式消息",
    })
    assert "turn" in result1
    history_after_companion = result1["history"]
    
    # Verify companion message is in history
    companion_in_history = any(
        "陪伴模式消息" in turn.get("text", "") 
        for turn in history_after_companion 
        if turn.get("role") == "user"
    )
    assert companion_in_history, "Companion mode message should be in history"
    
    # Switch to work mode
    runtime_for_mode_test.handle({"action": "set_mode", "mode": "work"})
    
    # Second message in work mode
    result2 = runtime_for_mode_test.handle({
        "action": "send_message",
        "text": "工作模式消息",
    })
    assert "turn" in result2
    history_after_work = result2["history"]
    
    # Verify work message is NOT in history (or history didn't grow)
    # Work mode should skip persistence, so history should be same or shorter
    work_in_history = any(
        "工作模式消息" in turn.get("text", "") 
        for turn in history_after_work 
        if turn.get("role") == "user"
    )
    assert not work_in_history, "Work mode message should NOT be in history"



def test_work_mode_still_returns_response(runtime_for_mode_test: DesktopRuntime) -> None:
    """Work mode still generates and returns responses, just doesn't persist."""
    runtime_for_mode_test.handle({"action": "bootstrap"})
    runtime_for_mode_test.handle({"action": "set_mode", "mode": "work"})
    
    result = runtime_for_mode_test.handle({
        "action": "send_message",
        "text": "你好",
    })
    
    assert "turn" in result
    assert "text" in result["turn"]
    assert len(result["turn"]["text"]) > 0
