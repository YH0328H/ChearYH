"""Deterministic local decision and expression adapters for the runtime."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Decision:
    speak: bool
    reason: str
    priority: float
    kind: str = "respond"


@dataclass(frozen=True)
class Expression:
    text: str
    kind: str
    emotion: str
    follow_up: bool = False


@dataclass(frozen=True)
class DecisionConfig:
    low_battery_threshold: float = 0.2
    low_impulse_threshold: float = 0.15
    default_priority: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.low_battery_threshold <= 1 or not 0 <= self.low_impulse_threshold <= 1:
            raise ValueError("decision thresholds must be within [0, 1]")
        if not 0 <= self.default_priority <= 1:
            raise ValueError("default_priority must be within [0, 1]")


@dataclass(frozen=True)
class ExpressionConfig:
    full_battery_threshold: float = 0.35
    short_prefix: str = ""
    refusal_text: str = "我现在有点累，但还在听。"

    def __post_init__(self) -> None:
        if not 0 <= self.full_battery_threshold <= 1:
            raise ValueError("full_battery_threshold must be within [0, 1]")


def load_cognition_config(path: Path) -> tuple[DecisionConfig, ExpressionConfig]:
    """Load validated local decision/expression defaults from TOML."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    decision = DecisionConfig(**raw.get("decision", {}))
    expression = ExpressionConfig(**raw.get("expression", {}))
    return decision, expression


class LocalDecisionProvider:
    """Resolve speak/listen from explicit foreground, gate and state evidence."""

    def __init__(self, config: DecisionConfig = DecisionConfig()) -> None:
        self.config = config

    def decide(self, request: Mapping[str, Any]) -> Decision:
        context = request.get("context")
        perception = getattr(context, "perception", None)
        if isinstance(perception, dict) and perception.get("sleeping"):
            return Decision(False, "sleeping", 1.0, "listen")
        gate_reason = request.get("gate_reason")
        if gate_reason:
            return Decision(False, str(gate_reason), 1.0, "listen")
        state = request.get("state", {})
        battery = _unit(state.get("social_battery", 0.8))
        impulse = _unit(state.get("expression_impulse", 0.5))
        if battery <= self.config.low_battery_threshold:
            return Decision(True, "low_battery_soft_refusal", self.config.default_priority, "soft_refusal")
        if impulse <= self.config.low_impulse_threshold:
            return Decision(False, "low_expression_impulse", self.config.default_priority, "listen")
        return Decision(True, "foreground_turn", self.config.default_priority)


class LocalExpressionProvider:
    """Render a deterministic text expression without inventing model content."""

    def __init__(self, config: ExpressionConfig = ExpressionConfig()) -> None:
        self.config = config

    def express(self, decision: Decision, request: Mapping[str, Any]) -> Expression:
        if not decision.speak:
            return Expression("", "silent", "neutral")
        if decision.kind == "soft_refusal":
            return Expression(self.config.refusal_text, "soft_refusal", "tired")
        context = request.get("context")
        perception = getattr(context, "perception", None)
        description = perception.get("description", "") if isinstance(perception, dict) else ""
        if not description:
            return Expression("我在听。", "short", "calm")
        text = str(description).strip()
        kind = "short" if _unit(request.get("state", {}).get("social_battery", 0.8)) < self.config.full_battery_threshold else "full"
        if self.config.short_prefix:
            text = self.config.short_prefix + text
        return Expression(text, kind, "calm")


def _unit(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
