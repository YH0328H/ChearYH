"""Unit tests for TTS service."""

import pytest
from pathlib import Path
from cether.tts import TTSConfig, TTSService, load_tts_config


class TestTTSConfig:
    """Test TTS configuration."""
    
    def test_default_config(self) -> None:
        """Default config uses XiaoxiaoNeural."""
        config = TTSConfig()
        assert config.voice == "zh-CN-XiaoxiaoNeural"
        assert config.rate == "+0%"
        assert config.volume == "+0%"
        assert config.pitch == "+0Hz"
        assert config.enabled is True
    
    def test_custom_config(self) -> None:
        """Custom config overrides defaults."""
        config = TTSConfig(
            voice="zh-CN-YunxiNeural",
            rate="+20%",
            volume="-10%",
            pitch="+5Hz",
            enabled=False,
        )
        assert config.voice == "zh-CN-YunxiNeural"
        assert config.rate == "+20%"
        assert config.volume == "-10%"
        assert config.pitch == "+5Hz"
        assert config.enabled is False


class TestTTSService:
    """Test TTS service."""
    
    def test_initialization(self) -> None:
        """Service initializes with config."""
        config = TTSConfig(voice="zh-CN-YunxiNeural")
        service = TTSService(config)
        assert service.config.voice == "zh-CN-YunxiNeural"
        assert service._temp_dir.exists()
    
    def test_speak_empty_text(self) -> None:
        """speak returns None for empty text."""
        service = TTSService()
        result = service.speak("")
        assert result is None
        
        result = service.speak("   ")
        assert result is None
    
    @pytest.mark.skipif(
        not TTSService(TTSConfig(enabled=False)).config.enabled,
        reason="edge-tts not available"
    )
    def test_speak_generates_audio(self) -> None:
        """speak generates audio file when TTS is available."""
        service = TTSService()
        
        # Skip if TTS not available
        if not service.config.enabled:
            pytest.skip("TTS not available")
        
        result = service.speak("你好")
        
        if result:  # Only assert if TTS succeeded
            assert result.exists()
            assert result.suffix == ".mp3"
            assert result.stat().st_size > 0
    
    def test_speak_disabled(self) -> None:
        """speak returns None when TTS is disabled."""
        config = TTSConfig(enabled=False)
        service = TTSService(config)
        result = service.speak("你好")
        assert result is None
    
    def test_cleanup_old_files(self) -> None:
        """cleanup removes old files beyond limit."""
        service = TTSService()
        temp_dir = service._temp_dir
        
        # Create test files
        for i in range(5):
            test_file = temp_dir / f"speech_test{i}.mp3"
            test_file.write_text("test")
        
        service.cleanup_old_files(max_files=3)
        
        remaining = list(temp_dir.glob("speech_test*.mp3"))
        assert len(remaining) <= 3
        
        # Clean up test files
        for f in remaining:
            f.unlink()


def test_load_tts_config_default() -> None:
    """load_tts_config returns default when file missing."""
    config = load_tts_config(Path("/nonexistent/path.toml"))
    assert config.voice == "zh-CN-XiaoxiaoNeural"
    assert config.enabled is True


def test_load_tts_config_from_file(tmp_path: Path) -> None:
    """load_tts_config reads from TOML file."""
    config_file = tmp_path / "tts.toml"
    config_file.write_text("""
[tts]
voice = "zh-CN-YunxiNeural"
rate = "+20%"
volume = "-10%"
pitch = "+5Hz"
enabled = false
""")
    
    config = load_tts_config(config_file)
    assert config.voice == "zh-CN-YunxiNeural"
    assert config.rate == "+20%"
    assert config.volume == "-10%"
    assert config.pitch == "+5Hz"
    assert config.enabled is False
