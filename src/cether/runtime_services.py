"""Concrete composition of role-scoped domain services for RuntimePipeline.

Provider-dependent narrative, decision and expression remain explicit inputs;
objective memory, trigger evaluation, state persistence and feedback are wired here.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .l0 import L0Archive
from .memory_tiering import classify_memory_tier
from .l1 import L1Archive, L1Record
from .narrative import NarrativeConfig, Post, generate_narrative
from .roles import RoleContext, RoleRegistry
from .runner import RuntimeConfig, RuntimePipeline, RuntimeSteps, ScopeGuard
from .state import StateSnapshot
from .trigger import EventContext, TriggerConfig, should_trigger_l1
from .proactive import ProactiveCandidate, ProactiveScheduler, load_proactive_config
from .tts import TTSService, TTSConfig, load_tts_config
from .backchannel import BackchannelScheduler, BackchannelHandle, BackchannelConfig


@dataclass(frozen=True)
class FeedbackConfig:
    full_expression_cost: float = 0.1
    short_expression_cost: float = 0.05
    soft_refusal_recovery: float = 0.01

    def __post_init__(self) -> None:
        if any(v < 0 or v > 1 for v in (self.full_expression_cost, self.short_expression_cost, self.soft_refusal_recovery)):
            raise ValueError("feedback amounts must be between 0 and 1")
class RuntimeServices:
    """Bind concrete per-role archives/state to pipeline with provider callbacks."""

    def __init__(
        self,
        *,
        role: RoleContext,
        registry: ScopeGuard,
        trigger_config: TriggerConfig,
        perceive: Callable[[], Any],
        decision: Callable[[dict[str, Any]], Any],
        expression: Callable[[Any, dict[str, Any]], Any],
        event_metadata: Callable[[Any], dict[str, Any]] = lambda _event: {},
        narrative_config: NarrativeConfig | None = None,
        narrative_post: Post | None = None,
        feedback_config: FeedbackConfig = FeedbackConfig(),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_consolidation: Callable[[RoleContext, dict[str, Any]], Any] | None = None,
        reflection: Callable[[RoleContext, dict[str, Any]], dict[str, Any] | None] | None = None,
        retrieval_index_update: Callable[[RoleContext], Any] | None = None,
        spatial_provider: Callable[[str, list[dict]], list[Any]] | None = None,
        embedding_provider: Callable[[list[str]], list[list[float]]] | None = None,
        graph_provider: Callable[[list[dict]], Any] | None = None,
        sleep_mode: Callable[[RoleContext, datetime], str] | None = None,
        gate_reason: Callable[[RoleContext, Any], str | None] | None = None,
        mode_provider: Callable[[], str] | None = None,
    ) -> None:
        if (narrative_config is None) != (narrative_post is None):
            raise ValueError("narrative_config and narrative_post must be supplied together")
        self.role = role
        self.registry = registry
        self.trigger_config = trigger_config
        self.perception_provider = perceive
        self.event_metadata = event_metadata
        self.decision_provider = decision
        self.expression_provider = expression
        self.narrative_config = narrative_config
        self.narrative_post = narrative_post
        self.feedback_config = feedback_config
        self.clock = clock
        self.sleep_provider = sleep_consolidation
        self.reflection_provider = reflection
        self.retrieval_index_provider = retrieval_index_update
        self.spatial_provider = spatial_provider
        self.embedding_provider = embedding_provider
        self.graph_provider = graph_provider
        self.sleep_mode_provider = sleep_mode
        self.gate_reason_provider = gate_reason
        self.mode_provider = mode_provider
        self._sleep_mode = "awake"
        self._sleep_active = False
        self._sleep_interrupted = False
        self._sleep_interrupted_mode: str | None = None
        self._last_gate_reason: str | None = None
        self._lock = threading.RLock()
        self._state_path = role.workspace / "state.json"
        self._state = self._load_state()
        self._pending_wake = self._load_pending_wake()
        self._pipeline: RuntimePipeline | None = None
        self._unregister_canceller = None
        self._closed = False
        if hasattr(registry, "register_task_canceller"):
            self._unregister_canceller = registry.register_task_canceller(role.config.role_id, self.cancel)
        self._l0 = L0Archive(role.workspace / "memory" / "l0.jsonl")
        self._l1 = L1Archive(role.workspace / "memory" / "l1.jsonl")

        # Proactive expression scheduler
        proactive_config_path = role.workspace.parent.parent / "config" / "proactive.toml"
        if proactive_config_path.exists():
            proactive_cfg = load_proactive_config(proactive_config_path)
            self.proactive_scheduler = ProactiveScheduler(proactive_cfg)
        else:
            self.proactive_scheduler = None

        # Initialize TTS service
        tts_cfg_path = role.workspace.parent.parent / "config" / "tts.toml"
        tts_cfg = load_tts_config(tts_cfg_path) if tts_cfg_path.exists() else TTSConfig()
        self.tts_service = TTSService(tts_cfg)
        
        # Initialize backchannel scheduler
        def deliver_backchannel(handle: BackchannelHandle) -> None:
            """Deliver backchannel response via TTS."""
            if handle.may_enqueue_tts():
                audio_path = self.tts_service.speak(handle.text)
                if audio_path:
                    # TODO: Queue audio playback (requires frontend integration)
                    print(f"[Backchannel] Generated TTS: {handle.text} -> {audio_path}")
        
        self.backchannel = BackchannelScheduler(deliver=deliver_backchannel)

    def get_current_mode(self) -> str:
        """Return current mode from mode provider or default to companion."""
        if self.mode_provider:
            try:
                return self.mode_provider()
            except Exception:
                pass
        return "companion"
        self._recent_themes: list[tuple[datetime, str]] = []
        self.retrieval_bias: dict[str, float] = self._load_retrieval_bias()

    def close(self) -> None:
        """Unregister lifecycle callback after disposing this service composition."""
        if not self.cancel():
            raise RuntimeError("runtime did not stop before close")
        self._closed = True
        unregister = self._unregister_canceller
        self._unregister_canceller = None
        if unregister is not None:
            unregister()

    def build_pipeline(self, *, interval_seconds: float = 5.0, event_sink=None) -> RuntimePipeline:
        """Build pipeline with real archives/state and injected decision/expression providers."""
        if self._closed:
            raise RuntimeError("runtime services are closed")
        steps = RuntimeSteps(
            perceive=self._perceive,
            append_l0=self._append_l0,
            should_trigger_l1=self._trigger,
            generate_l1=self._generate_l1,
            update_state=self._update_state,
            decide=lambda context, state: self.decision_provider({"context": context, "state": state,
                                                                  "retrieval_bias": dict(self.retrieval_bias),
                                                                  "role": self.role,
                                                                  "gate_reason": self._last_gate_reason}),
            express=lambda context, decision: self.expression_provider(decision, {"context": context, "role": self.role}),
            feed_result=self._feed_result,
            sleep_consolidation=self._sleep if self.sleep_provider else None,
            reflection_calibration=self._reflect if self.reflection_provider else None,
            retrieval_bias_update=self._update_retrieval_bias if self.retrieval_index_provider else None,
            should_process=self._gate_reason if self.gate_reason_provider else None,
        )
        self._pipeline = RuntimePipeline(role_scope=self.role.scope_id, scope_guard=self.registry, steps=steps,
                                        config=RuntimeConfig(interval_seconds=interval_seconds), event_sink=event_sink)
        return self._pipeline

    def cancel(self) -> bool:
        """Stop this role's active pipeline before its workspace is released."""
        if self._pipeline is None:
            return True
        return self._pipeline.cancel(timeout=30.0)

    def pending_wake_context(self) -> str | None:
        """Render the pending wake context without consuming its one-time injection."""
        self.registry.ensure_role_scope(self.role.scope_id)
        payload = self._pending_wake
        if payload is None:
            return None
        from .wake import render_injection
        return render_injection(payload)

    def begin_user_turn(self) -> str | None:
        """Return pending wake context once and interrupt a scheduled sleep mode."""
        self.registry.ensure_role_scope(self.role.scope_id)
        if self._sleep_active and self._sleep_mode in {"light", "deep"}:
            self._sleep_interrupted = True
            self._sleep_interrupted_mode = self._sleep_mode
            self._sleep_mode = "awake"
        text = self.pending_wake_context()
        if text is None:
            return None
        self.registry.mark_first_turn_consumed(self.role.config.role_id)
        self._pending_wake = None
        return text

    def decide_user_turn(self, context: Any, state: StateSnapshot, wake_context: str | None = None) -> Any:
        """Run a user-initiated decision with optional one-time wake context."""
        self.registry.ensure_role_scope(self.role.scope_id)
        wake = self.begin_user_turn() if wake_context is None else wake_context
        return self.decision_provider({"context": context, "state": state,
                                       "retrieval_bias": dict(self.retrieval_bias),
                                       "role": self.role, "wake_context": wake})

    def _load_pending_wake(self):
        from .roles import RoleRegistry

        if not isinstance(self.registry, RoleRegistry):
            return None
        return self.registry.pending_wake(self.role.config.role_id)

    def _gate_reason(self, event: Any) -> str | None:
        self.registry.ensure_role_scope(self.role.scope_id)
        self._last_gate_reason = None
        reason = self.gate_reason_provider(self.role, event)
        self._last_gate_reason = str(reason) if reason else None
        return self._last_gate_reason

    def _perceive(self) -> Any:
        self.registry.ensure_role_scope(self.role.scope_id)
        mode = self.sleep_mode_provider(self.role, self.clock()) if self.sleep_mode_provider else "awake"
        self._sleep_mode = str(mode)
        self._sleep_active = self._sleep_mode in {"light", "deep"}
        if mode in {"light", "deep"} and not self._sleep_interrupted:
            return {"sleeping": True, "sleep_mode": mode}
        if self._sleep_interrupted:
            self._sleep_interrupted = False
            interrupted_mode = self._sleep_interrupted_mode
            self._sleep_interrupted_mode = None
            return {"sleeping": False, "sleep_mode": "awake", "sleep_interrupted": True, "interrupted_sleep_mode": interrupted_mode}
        event = self.perception_provider()
        if isinstance(event, dict):
            return {**event, "sleep_mode": mode}
        return event

    def _append_l0(self, event: Any) -> str | None:
        text = _event_text(event)
        if not text or _event_value(event, "changed", True) is False:
            return None
        metadata = self.event_metadata(event)
        source = str(metadata.get("source", "perception"))
        requested_weight = str(metadata.get("weight", "normal"))
        if requested_weight == "low":
            weight = "low"
        else:
            tier = classify_memory_tier(metadata)
            weight = "normal"
            if tier == "high":
                metadata = {**metadata, "memory_tier": "high"}
        return self._l0.append(text, source, weight, metadata=metadata)

    def _trigger(self, event: Any, l0_id: str | None) -> bool:
        if not l0_id:
            return False
        metadata = self.event_metadata(event)
        theme = metadata.get("theme")
        trigger = EventContext(
            ts=self.clock(), manual_mark=bool(metadata.get("manual_mark", False)),
            is_relation_event=bool(metadata.get("is_relation_event", False)),
            emotion_intensity=float(metadata.get("emotion_intensity", 0.0)),
            salience=float(metadata.get("salience", 0.0)),
            theme=str(theme) if theme else None,
        )
        result = should_trigger_l1(trigger, self.trigger_config, self._recent_themes)
        if trigger.theme:
            self._recent_themes.append((trigger.ts, trigger.theme))
            cutoff = trigger.ts.timestamp() - self.trigger_config.repetition_window_seconds
            self._recent_themes = [(ts, item) for ts, item in self._recent_themes if ts.timestamp() >= cutoff]
        return result

    def _generate_l1(self, event: Any, l0_id: str | None) -> dict[str, Any] | None:
        if not l0_id or not self.narrative_config or not self.narrative_post:
            return None
        raw = generate_narrative(self.narrative_config, [_event_text(event)], self.narrative_post)
        self._l1.append(L1Record(self.clock(), raw["narrative"], raw.get("emotion_tag"),
                                 raw.get("relation_tag"), [l0_id]))
        return raw

    def _update_state(self, event: Any, narrative: Any) -> dict[str, Any]:
        if _event_value(event, "sleeping", False):
            return self._read_state()
        with self._lock:
            dimensions = dict(self._state.dimensions)
            if narrative and narrative.get("emotion_tag"):
                dimensions["last_emotion_tag"] = narrative["emotion_tag"]
            self._state = StateSnapshot(self.clock().timestamp(), dimensions)
            self._save_state()
            return dimensions

    def _feed_result(self, context: Any, expression: Any, state: Any) -> dict[str, Any]:
        """Persist expression battery cost and its emotional residue after expression completes."""
        if context is not None and _event_value(getattr(context, "perception", None), "sleeping", False):
            return {"frozen": True}
        kind = str(_event_value(expression, "kind", "full"))
        cfg = self.feedback_config
        cost = cfg.short_expression_cost if kind == "short" else 0.0 if kind == "soft_refusal" else cfg.full_expression_cost
        with self._lock:
            dimensions = dict(self._state.dimensions)
            battery = float(dimensions.get("social_battery", 0.8))
            if kind == "soft_refusal":
                battery = min(1.0, battery + cfg.soft_refusal_recovery)
            else:
                battery = max(0.0, battery - cost)
            dimensions["social_battery"] = battery
            dimensions["emotional_residue"] = str(_event_value(expression, "emotion", "neutral"))
            self._state = StateSnapshot(self.clock().timestamp(), dimensions)
            self._save_state()
            return {"social_battery": battery, "emotional_residue": dimensions["emotional_residue"]}

    def _sleep(self, _context: Any) -> Any:
        return self.sleep_provider(self.role, self._read_state())

    def _reflect(self, _context: Any) -> Any:
        result = self.reflection_provider(self.role, self._read_state())
        if result:
            with self._lock:
                dimensions = dict(self._state.dimensions)
                dimensions.update(result.get("baseline", {}))
                self._state = StateSnapshot(self.clock().timestamp(), dimensions)
                self._save_state()
                narrative = result.get("narrative")
                source_ids = result.get("source_l0_ids", [])
                if narrative and source_ids:
                    self._l1.append(L1Record(self.clock(), str(narrative), "reflection", "self",
                                             [str(item) for item in source_ids]))
                bias = result.get("retrieval_bias")
                if isinstance(bias, dict):
                    self.retrieval_bias = {str(key): float(value) for key, value in bias.items()}
                    _atomic_json(self.role.workspace / "retrieval_bias.json", self.retrieval_bias)
        return result

    def _update_retrieval_bias(self, _context: Any) -> Any:
        result = self.retrieval_index_provider(self.role)
        if isinstance(result, dict):
            self.retrieval_bias = {str(k): float(v) for k, v in result.items()}
            _atomic_json(self.role.workspace / "retrieval_bias.json", self.retrieval_bias)
        return result

    def _load_retrieval_bias(self) -> dict[str, float]:
        path = self.role.workspace / "retrieval_bias.json"
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): float(value) for key, value in raw.items()}

    def _read_state(self) -> dict[str, Any]:
        with self._lock:
            # Support both StateSnapshot and dict (for testing)
            if isinstance(self._state, dict):
                return dict(self._state)
            return dict(self._state.dimensions)

    def _load_state(self) -> StateSnapshot:
        if not self._state_path.exists():
            return StateSnapshot(self.clock().timestamp(), {"social_battery": 0.8})
        raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        return StateSnapshot(float(raw.get("timestamp", self.clock().timestamp())), dict(raw.get("dimensions", raw)))

    def _save_state(self) -> None:
        _atomic_json(self._state_path, {"timestamp": self._state.timestamp, "dimensions": self._state.dimensions})


def _event_value(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)


def _event_text(event: Any) -> str:
    if isinstance(event, str):
        return event
    description = _event_value(event, "description")
    if description:
        return str(description)
    return "" if event is None else ""



    def tick_proactive_scheduler(self, context: dict[str, Any]) -> ProactiveCandidate | None:
        """Run one proactive scheduler tick. Returns a candidate if one passes gates."""
        if self.proactive_scheduler is None:
            return None
        
        return self.proactive_scheduler.tick(context)
    
    def generate_proactive_expression(
        self,
        candidate: ProactiveCandidate,
        state: dict[str, Any],
        provider: Any,
    ) -> dict[str, Any] | None:
        """Generate expression text for a proactive candidate using the expression provider."""
        # Build a minimal request for the expression provider
        request = {
            "kind": "proactive",
            "trigger": candidate.trigger_kind,
            "reason": candidate.reason,
            "topic": candidate.topic,
            "metadata": candidate.metadata,
            "state": state,
        }
        
        try:
            # Use the expression provider to generate appropriate text
            if hasattr(provider, "generate_proactive"):
                response = provider.generate_proactive(request)
            else:
                # Fallback: use default templates
                response = self._default_proactive_template(candidate)
            
            return response
        except Exception as exc:
            return None
    
    def _default_proactive_template(self, candidate: ProactiveCandidate) -> dict[str, Any]:
        """Provide default proactive expression templates."""
        templates = {
            "idle": "好久没见到你了，在忙什么呢？",
            "stress": "看起来遇到困难了，需要帮助吗？",
            "mindbox": f"你之前提到的{candidate.topic or '那件事'}，现在怎么样了？",
            "weather": "天气变化了，记得注意一下~",
        }
        
        text = templates.get(candidate.trigger_kind, "在想你呢~")
        
        return {
            "text": text,
            "kind": "proactive",
            "emotion": "gentle",
            "directive": {},
        }

def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
