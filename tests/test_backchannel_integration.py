"""Integration tests for backchannel with TTS."""

import pytest
from pathlib import Path
from cether.desktop import DesktopRuntime


@pytest.fixture
def runtime_with_backchannel(tmp_path: Path) -> DesktopRuntime:
    """Create a runtime with backchannel enabled."""
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
    
    # Create TTS config (disabled for testing)
    (config_dir / "tts.toml").write_text('[tts]\nenabled = false', encoding="utf-8")
    
    runtime = DesktopRuntime(data_dir=data_dir)
    
    # Bootstrap with a test role
    runtime.handle({"action": "bootstrap"})
    runtime.handle({
        "action": "create_role",
        "name": "BackchannelTest",
        "persona": {"name": "Test", "traits": []},
    })
    
    return runtime


def test_backchannel_no_match(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel returns not acknowledged when no rule matches."""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "Hello world",
    })
    
    assert result["acknowledged"] is False


def test_backchannel_thank_you_match(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel acknowledges '谢谢' with '嗯，收到。'"""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "谢谢你的帮助",
    })
    
    assert result["acknowledged"] is True
    assert result["text"] == "嗯，收到。"
    assert "handle_id" in result


def test_backchannel_question_match(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel acknowledges questions with '我想一下。'"""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "你觉得怎么样？",
    })
    
    assert result["acknowledged"] is True
    assert result["text"] == "我想一下。"


def test_backchannel_sad_match(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel acknowledges sad expressions with '我在听。'"""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "今天真难过",
    })
    
    assert result["acknowledged"] is True
    assert result["text"] == "我在听。"


def test_backchannel_greeting_match(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel acknowledges greetings with '嗨。'"""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "你好呀",
    })
    
    assert result["acknowledged"] is True
    assert result["text"] == "嗨。"


def test_backchannel_empty_text(runtime_with_backchannel: DesktopRuntime) -> None:
    """backchannel returns not acknowledged for empty text."""
    result = runtime_with_backchannel.handle({
        "action": "backchannel",
        "text": "",
    })
    
    assert result["acknowledged"] is False
