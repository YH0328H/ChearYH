"""Text-to-speech service using Edge TTS."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False


@dataclass
class TTSConfig:
    """Configuration for TTS service."""
    
    voice: str = "zh-CN-XiaoxiaoNeural"  # 默认使用晓晓（女声）
    rate: str = "+0%"  # 语速：-50% 到 +100%
    volume: str = "+0%"  # 音量：-50% 到 +50%
    pitch: str = "+0Hz"  # 音调：-50Hz 到 +50Hz
    enabled: bool = True


class TTSService:
    """Text-to-speech service with Edge TTS backend."""
    
    def __init__(self, config: TTSConfig = TTSConfig()) -> None:
        self.config = config
        self._temp_dir = Path(tempfile.gettempdir()) / "cether_tts"
        self._temp_dir.mkdir(exist_ok=True)
        
        if not EDGE_TTS_AVAILABLE:
            print("[TTS] Warning: edge-tts not installed, TTS disabled")
            self.config.enabled = False
    
    async def speak_async(self, text: str) -> Path | None:
        """Generate speech audio file asynchronously.
        
        Returns:
            Path to generated audio file, or None if TTS is disabled or failed.
        """
        if not self.config.enabled or not EDGE_TTS_AVAILABLE:
            return None
        
        if not text.strip():
            return None
        
        try:
            # Generate unique filename
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            audio_path = self._temp_dir / f"speech_{text_hash}.mp3"
            
            # Use cached file if exists
            if audio_path.exists():
                return audio_path
            
            # Generate speech
            communicate = edge_tts.Communicate(
                text,
                voice=self.config.voice,
                rate=self.config.rate,
                volume=self.config.volume,
                pitch=self.config.pitch,
            )
            
            await communicate.save(str(audio_path))
            return audio_path
            
        except Exception as e:
            print(f"[TTS] Error generating speech: {e}")
            return None
    
    def speak(self, text: str) -> Path | None:
        """Generate speech audio file synchronously.
        
        Returns:
            Path to generated audio file, or None if TTS is disabled or failed.
        """
        try:
            return asyncio.run(self.speak_async(text))
        except RuntimeError:
            # If event loop is already running, create new loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.speak_async(text))
            finally:
                loop.close()
    
    def cleanup_old_files(self, max_files: int = 50) -> None:
        """Remove old temporary audio files if count exceeds limit."""
        try:
            files = sorted(self._temp_dir.glob("speech_*.mp3"), key=lambda p: p.stat().st_mtime)
            if len(files) > max_files:
                for file in files[:-max_files]:
                    file.unlink()
        except Exception as e:
            print(f"[TTS] Error cleaning up files: {e}")


def load_tts_config(path: Path) -> TTSConfig:
    """Load TTS configuration from TOML file."""
    import tomllib
    
    if not path.exists():
        return TTSConfig()
    
    with open(path, "rb") as f:
        data = tomllib.load(f)
    
    tts_data = data.get("tts", {})
    return TTSConfig(
        voice=tts_data.get("voice", "zh-CN-XiaoxiaoNeural"),
        rate=tts_data.get("rate", "+0%"),
        volume=tts_data.get("volume", "+0%"),
        pitch=tts_data.get("pitch", "+0Hz"),
        enabled=tts_data.get("enabled", True),
    )
