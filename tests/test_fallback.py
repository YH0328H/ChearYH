"""Tests for provider fallback mechanism."""

import pytest
from pathlib import Path
from cether.providers import (
    LocalRuleProvider,
    OpenAICompatibleProvider,
    FallbackProvider,
    OllamaProvider,
    ProviderConfig,
    TurnRequest,
    ProviderError,
)


class MockFailingProvider:
    """Provider that always fails."""
    
    def respond(self, request: TurnRequest) -> None:
        raise ProviderError("Mock failure")


class MockSuccessProvider:
    """Provider that always succeeds."""
    
    def respond(self, request: TurnRequest):
        from cether.providers import TurnResponse
        return TurnResponse(text="Mock success", kind="short", emotion="calm")


def test_local_rule_provider_always_works() -> None:
    """LocalRuleProvider never fails."""
    provider = LocalRuleProvider()
    request = TurnRequest(
        role_name="Test",
        user_text="Hello",
        persona="Test persona",
        state={},
        self_awareness=5,
        recent_memories=[],
        wake_context=None,
    )
    
    response = provider.respond(request)
    assert response.text.startswith("Test：")
    assert "Hello" in response.text


def test_fallback_uses_primary_when_it_succeeds() -> None:
    """FallbackProvider uses primary when it works."""
    primary = MockSuccessProvider()
    fallback = FallbackProvider(primary=primary)
    
    request = TurnRequest(
        role_name="Test",
        user_text="Hello",
        persona="Test persona",
        state={},
        self_awareness=5,
        recent_memories=[],
        wake_context=None,
    )
    
    response = fallback.respond(request)
    assert response.text == "Mock success"


def test_fallback_uses_rule_when_primary_fails() -> None:
    """FallbackProvider falls back to rule when primary fails."""
    primary = MockFailingProvider()
    fallback = FallbackProvider(primary=primary)
    
    request = TurnRequest(
        role_name="Test",
        user_text="Hello",
        persona="Test persona",
        state={},
        self_awareness=5,
        recent_memories=[],
        wake_context=None,
    )
    
    response = fallback.respond(request)
    assert response.text.startswith("Test：")  # LocalRuleProvider format


def test_fallback_tries_ollama_before_rule() -> None:
    """FallbackProvider tries Ollama before rule when enabled."""
    primary = MockFailingProvider()
    ollama_config = ProviderConfig(
        base_url="http://localhost:11434/v1",
        model_id="qwen2.5:3b",
        temperature=0.7,
        key_env="",
    )
    
    fallback = FallbackProvider(
        primary=primary,
        enable_ollama=True,
        ollama_config=ollama_config,
    )
    
    request = TurnRequest(
        role_name="Test",
        user_text="Hello",
        persona="Test persona",
        state={},
        self_awareness=5,
        recent_memories=[],
        wake_context=None,
    )
    
    # Will fail to Ollama (not running), then to rule
    response = fallback.respond(request)
    assert response.text.startswith("Test：")


def test_ollama_provider_config() -> None:
    """OllamaProvider uses correct default config."""
    config = ProviderConfig(
        base_url="ignored",  # Will be overridden
        model_id="custom-model",
        temperature=0.8,
        key_env="ignored",
    )
    
    ollama = OllamaProvider(config)
    assert ollama.config.base_url == "http://localhost:11434/v1"
    assert ollama.config.model_id == "custom-model"
    assert ollama.config.temperature == 0.8
    assert ollama.config.key_env == ""  # No key needed
