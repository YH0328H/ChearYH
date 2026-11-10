"""Proactive expression scheduler with triggers, gates, and priority resolution.

The scheduler periodically evaluates candidate proactive expressions based on:
- Idle detection (no user interaction for threshold)
- Stress detection (screen content contains stress keywords)
- MindBox review (check unresolved concerns from lookback window)
- Weather events (optional external API integration)

Each candidate must pass all configured gates before being eligible:
- Awake gate: role must not be sleeping
- Window gate: user must be in active window
- Silent mode gate: role must not be in silent mode
- Cooldown gate: sufficient time since last proactive expression
- Frequency gate: daily limit not exceeded

The highest-priority passing candidate is selected for expression.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TriggerConfig:
    """Configuration for one trigger type."""
    enabled: bool
    cooldown: float  # seconds
    priority: float  # 0.0-1.0
    
    def __post_init__(self) -> None:
        if not 0 <= self.priority <= 1:
            raise ValueError("priority must be in [0, 1]")
        if self.cooldown < 0:
            raise ValueError("cooldown must be non-negative")


@dataclass(frozen=True)
class IdleTriggerConfig(TriggerConfig):
    threshold_seconds: float = 1800.0


@dataclass(frozen=True)
class StressTriggerConfig(TriggerConfig):
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class MindBoxTriggerConfig(TriggerConfig):
    lookback_days: int = 14


@dataclass(frozen=True)
class WeatherTriggerConfig(TriggerConfig):
    pass


@dataclass(frozen=True)
class SchedulerConfig:
    check_interval: float = 300.0  # seconds
    global_cooldown: float = 1800.0
    frequency_limit: int = 10  # per day
    
    def __post_init__(self) -> None:
        if self.check_interval <= 0 or self.global_cooldown < 0:
            raise ValueError("intervals must be positive")
        if self.frequency_limit < 0:
            raise ValueError("frequency_limit must be non-negative")


@dataclass(frozen=True)
class GateConfig:
    require_awake: bool = True
    require_window_active: bool = True
    respect_silent_mode: bool = True


@dataclass(frozen=True)
class ProactiveConfig:
    scheduler: SchedulerConfig
    idle: IdleTriggerConfig
    stress: StressTriggerConfig
    mindbox: MindBoxTriggerConfig
    weather: WeatherTriggerConfig
    gates: GateConfig


def load_proactive_config(path: Path) -> ProactiveConfig:
    """Load and validate proactive expression configuration from TOML."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    
    scheduler = SchedulerConfig(**raw.get("scheduler", {}))
    
    idle_raw = raw.get("triggers", {}).get("idle", {})
    idle = IdleTriggerConfig(
        enabled=idle_raw.get("enabled", True),
        cooldown=float(idle_raw.get("cooldown", 3600)),
        priority=float(idle_raw.get("priority", 0.5)),
        threshold_seconds=float(idle_raw.get("threshold_seconds", 1800)),
    )
    
    stress_raw = raw.get("triggers", {}).get("stress", {})
    stress = StressTriggerConfig(
        enabled=stress_raw.get("enabled", True),
        cooldown=float(stress_raw.get("cooldown", 7200)),
        priority=float(stress_raw.get("priority", 0.8)),
        keywords=tuple(stress_raw.get("keywords", [])),
    )
    
    mindbox_raw = raw.get("triggers", {}).get("mindbox", {})
    mindbox = MindBoxTriggerConfig(
        enabled=mindbox_raw.get("enabled", True),
        cooldown=float(mindbox_raw.get("cooldown", 86400)),
        priority=float(mindbox_raw.get("priority", 0.7)),
        lookback_days=int(mindbox_raw.get("lookback_days", 14)),
    )
    
    weather_raw = raw.get("triggers", {}).get("weather", {})
    weather = WeatherTriggerConfig(
        enabled=weather_raw.get("enabled", False),
        cooldown=float(weather_raw.get("cooldown", 43200)),
        priority=float(weather_raw.get("priority", 0.6)),
    )
    
    gates = GateConfig(**raw.get("gates", {}))
    
    return ProactiveConfig(scheduler, idle, stress, mindbox, weather, gates)


@dataclass(frozen=True)
class ProactiveCandidate:
    """One candidate proactive expression with its trigger source and priority."""
    trigger_kind: str
    priority: float
    reason: str
    topic: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class GateResult:
    """Result of gate checks for a candidate."""
    passed: bool
    blocked_by: str | None = None


class ProactiveScheduler:
    """Evaluate triggers, apply gates, and select the highest-priority candidate."""
    
    def __init__(self, config: ProactiveConfig) -> None:
        self.config = config
        self._last_proactive_ts: datetime | None = None
        self._last_trigger_ts: dict[str, datetime] = {}
        self._daily_count = 0
        self._daily_reset_date: datetime | None = None
    
    def evaluate_triggers(self, context: Mapping[str, Any]) -> list[ProactiveCandidate]:
        """Generate candidate expressions from enabled triggers."""
        candidates: list[ProactiveCandidate] = []
        now = datetime.now(timezone.utc)
        
        # Check per-trigger cooldowns
        def _trigger_ready(kind: str, cooldown: float) -> bool:
            last = self._last_trigger_ts.get(kind)
            if last is None:
                return True
            return (now - last).total_seconds() >= cooldown
        
        # IdleTrigger
        if self.config.idle.enabled and _trigger_ready("idle", self.config.idle.cooldown):
            last_interaction = context.get("last_interaction_ts")
            if isinstance(last_interaction, datetime):
                idle_seconds = (now - last_interaction).total_seconds()
                if idle_seconds >= self.config.idle.threshold_seconds:
                    candidates.append(ProactiveCandidate(
                        trigger_kind="idle",
                        priority=self.config.idle.priority,
                        reason="user_idle",
                        metadata={"idle_seconds": idle_seconds}
                    ))
        
        # StressTrigger
        if self.config.stress.enabled and _trigger_ready("stress", self.config.stress.cooldown):
            perception = context.get("perception", {})
            if isinstance(perception, dict):
                description = perception.get("description", "")
                if isinstance(description, str) and self.config.stress.keywords:
                    matched = [kw for kw in self.config.stress.keywords if kw.lower() in description.lower()]
                    if matched:
                        candidates.append(ProactiveCandidate(
                            trigger_kind="stress",
                            priority=self.config.stress.priority,
                            reason="stress_detected",
                            metadata={"matched_keywords": matched}
                        ))
        
        # MindBoxTrigger
        if self.config.mindbox.enabled and _trigger_ready("mindbox", self.config.mindbox.cooldown):
            mind_box = context.get("mind_box", [])
            if isinstance(mind_box, list) and mind_box:
                cutoff = now - timedelta(days=self.config.mindbox.lookback_days)
                old_concerns = [
                    item for item in mind_box
                    if isinstance(item, dict) and 
                    isinstance(item.get("ts"), datetime) and
                    item["ts"] <= cutoff and
                    not item.get("resolved", False)
                ]
                if old_concerns:
                    candidates.append(ProactiveCandidate(
                        trigger_kind="mindbox",
                        priority=self.config.mindbox.priority,
                        reason="mindbox_review",
                        topic=old_concerns[0].get("topic"),
                        metadata={"concern_count": len(old_concerns)}
                    ))
        
        # WeatherTrigger (placeholder - requires external API)
        if self.config.weather.enabled and _trigger_ready("weather", self.config.weather.cooldown):
            weather = context.get("weather")
            if isinstance(weather, dict) and weather.get("extreme"):
                candidates.append(ProactiveCandidate(
                    trigger_kind="weather",
                    priority=self.config.weather.priority,
                    reason="weather_event",
                    metadata={"condition": weather.get("condition")}
                ))
        
        return candidates
    
    def check_gates(self, context: Mapping[str, Any]) -> GateResult:
        """Apply all configured gates. Returns passed=True if all gates pass."""
        now = datetime.now(timezone.utc)
        
        # Awake gate
        if self.config.gates.require_awake:
            perception = context.get("perception", {})
            if isinstance(perception, dict) and perception.get("sleeping"):
                return GateResult(False, "sleeping")
        
        # Window gate
        if self.config.gates.require_window_active:
            window = context.get("window", {})
            if isinstance(window, dict):
                reason = window.get("checkpoint_block_reason")
                if reason:
                    return GateResult(False, str(reason))
        
        # Silent mode gate
        if self.config.gates.respect_silent_mode:
            mode = context.get("mode")
            if mode == "silent":
                return GateResult(False, "silent_mode")
        
        # Global cooldown gate
        if self._last_proactive_ts is not None:
            elapsed = (now - self._last_proactive_ts).total_seconds()
            if elapsed < self.config.scheduler.global_cooldown:
                return GateResult(False, "global_cooldown")
        
        # Frequency limit gate
        today = now.date()
        if self._daily_reset_date != today:
            self._daily_count = 0
            self._daily_reset_date = today
        if self._daily_count >= self.config.scheduler.frequency_limit:
            return GateResult(False, "frequency_limit")
        
        return GateResult(True)
    
    def select_candidate(
        self, 
        candidates: list[ProactiveCandidate], 
        context: Mapping[str, Any]
    ) -> ProactiveCandidate | None:
        """Select the highest-priority candidate that passes all gates."""
        gate_result = self.check_gates(context)
        if not gate_result.passed:
            return None
        
        if not candidates:
            return None
        
        # Sort by priority (highest first)
        sorted_candidates = sorted(candidates, key=lambda c: c.priority, reverse=True)
        return sorted_candidates[0]
    
    def record_expression(self, candidate: ProactiveCandidate) -> None:
        """Record that a proactive expression was sent."""
        now = datetime.now(timezone.utc)
        self._last_proactive_ts = now
        self._last_trigger_ts[candidate.trigger_kind] = now
        self._daily_count += 1
    
    def tick(self, context: Mapping[str, Any]) -> ProactiveCandidate | None:
        """Main scheduler tick: evaluate triggers, check gates, select candidate."""
        candidates = self.evaluate_triggers(context)
        return self.select_candidate(candidates, context)
