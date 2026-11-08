"""Model provider ports and adapters for explicit conversation turns."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderConfig:
    """Endpoint, model, key environment name, and request timeout."""

    base_url: str = "https://api.openai.com/v1"
    model_id: str = "gpt-4o-mini"
    key_env: str = "CETHER_CHAT_API_KEY"
    timeout_seconds: float = 45.0
    temperature: float = 0.7

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

    def api_key(self) -> str | None:
        value = os.environ.get(self.key_env, "").strip()
        return value or None


@dataclass(frozen=True)
class TurnRequest:
    role_name: str
    persona: str
    user_text: str
    state: dict[str, float]
    recent_memories: tuple[str, ...]
    wake_context: str | None = None
    self_awareness: str = "resident"


@dataclass(frozen=True)
class ExpressionDirective:
    tone: str | None = None
    expression: str | None = None
    action: str | None = None

    def __post_init__(self) -> None:
        if any(value is not None and not value.strip() for value in (self.tone, self.expression, self.action)):
            raise ValueError("expression directives must be non-empty when present")


@dataclass(frozen=True)
class TurnResponse:
    text: str
    kind: str = "full"
    emotion: str = "neutral"
    directive: ExpressionDirective | None = None


class ConversationProvider(Protocol):
    """Generate one assistant response for a role-scoped user turn."""

    def respond(self, request: TurnRequest) -> TurnResponse: ...


class ProviderError(RuntimeError):
    """A provider transport or response error suitable for UI reporting."""


class LocalRuleProvider:
    """Dependency-free local adapter used when no remote key is configured."""

    def respond(self, request: TurnRequest) -> TurnResponse:
        prefix = f"{request.role_name}："
        if request.wake_context:
            text = f"{prefix}我回来了，也记得上次停在这里。你刚才说：{request.user_text}"
        else:
            text = f"{prefix}我听到了：{request.user_text}"
        return TurnResponse(text=text, kind="short", emotion="calm")


class OpenAICompatibleProvider:
    """OpenAI Chat Completions adapter; key is resolved only from the environment."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def respond(self, request: TurnRequest) -> TurnResponse:
        key = self.config.api_key()
        if not key:
            raise ProviderError(f"API key is not set in {self.config.key_env}")
        system = [request.persona.strip(), f"你正在以角色{request.role_name}和用户对话。当前状态：{json.dumps(request.state, ensure_ascii=False)}"]
        system.append(f"角色卡自我认知档位：{request.self_awareness}。以该角色卡内容为准；不得替用户修改或推断该设定。")
        if request.recent_memories:
            system.append("近期记忆：\n" + "\n".join(f"- {item}" for item in request.recent_memories))
        if request.wake_context:
            system.append("本轮一次性唤醒上下文：\n" + request.wake_context)
        body = json.dumps({
            "model": self.config.model_id,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": "\n\n".join(part for part in system if part)},
                {"role": "user", "content": request.user_text},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"chat provider request failed: {exc}") from exc
        try:
            message = payload["choices"][0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("chat provider returned an unexpected response shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("chat provider returned an empty response")
        raw = message.get("expression_directive")
        directive = None
        if raw is not None:
            if not isinstance(raw, dict):
                raise ProviderError("chat provider returned an invalid expression directive")
            try:
                directive = ExpressionDirective(**raw)
            except (TypeError, ValueError) as exc:
                raise ProviderError("chat provider returned an invalid expression directive") from exc
        return TurnResponse(content.strip(), directive=directive)


def load_provider_config(path: str | os.PathLike[str]) -> ProviderConfig:
    """Load [chat] TOML configuration; credentials are never stored in the file."""
    import tomllib
    with open(path, "rb") as stream:
        raw = tomllib.load(stream).get("chat", {})
    return ProviderConfig(
        base_url=str(raw.get("base_url", ProviderConfig.base_url)),
        model_id=str(raw.get("model_id", ProviderConfig.model_id)),
        key_env=str(raw.get("key_env", ProviderConfig.key_env)),
        timeout_seconds=float(raw.get("timeout_seconds", ProviderConfig.timeout_seconds)),
        temperature=float(raw.get("temperature", ProviderConfig.temperature)),
    )
