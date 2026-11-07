"""Runtime assembly for perception and the full per-turn lifecycle.

The concrete domain modules remain independently testable. ``RuntimePipeline``
orders their injected operations, enforces the active role scope at each tick,
and records outcomes so UI and diagnostics can observe the main loop.
"""

from __future__ import annotations

import json
import time
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .perception import Perceiver, Thumbnail, Tick
from .vision import VisionConfig, VisionError, describe, load_vision_config

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class FrameBuffer:
    def __init__(self) -> None:
        self.png: bytes | None = None

    def clear(self) -> None:
        self.png = None


def http_post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise VisionError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc


def build_perceiver(
    *,
    vision_config_path: Path,
    world_log: Path,
    environ: Mapping[str, str],
    grab: Callable[[], tuple[Thumbnail, bytes]],
    foreground_app: Callable[[], str],
    post: Callable[[str, dict, dict], dict] = http_post,
) -> tuple[Perceiver, VisionConfig]:
    """Construct the screen observer and return its validated provider config."""
    cfg = load_vision_config(vision_config_path, environ)
    frame = FrameBuffer()

    def capture() -> Thumbnail:
        thumb, png = grab()
        frame.png = png
        return thumb

    def describe_frame() -> str:
        if frame.png is None:
            raise VisionError("no frame to describe")
        return describe(cfg, frame.png, post)

    perceiver = Perceiver(
        capture=capture,
        describe=describe_frame,
        world_log=world_log,
        foreground_app=foreground_app,
        release=frame.clear,
    )
    return perceiver, cfg


@dataclass(frozen=True)
class RuntimeConfig:
    """Main-loop policy. ``interval_seconds`` is sampled between completed ticks."""
    interval_seconds: float = 5.0
    background_failures_are_non_blocking: bool = True

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")


@dataclass(frozen=True)
class RuntimeContext:
    """Inputs and accumulated outputs for one role-scoped runtime tick."""
    tick_id: int
    role_scope: str
    started_at: datetime
    perception: Tick | None = None
    l0_id: str | None = None
    trigger: bool = False
    narrative: Any = None
    state: Any = None
    decision: Any = None
    expression: Any = None
    result: Any = None
    background_results: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    tick_id: int
    stage: str
    status: str
    role_scope: str
    timestamp: datetime
    detail: str = ""


@dataclass(frozen=True)
class RuntimeReport:
    ticks: int
    events: tuple[RuntimeEvent, ...]
    last_context: RuntimeContext | None
    stopped_reason: str


class ScopeGuard(Protocol):
    def ensure_role_scope(self, scope_id: str) -> Any: ...


@dataclass(frozen=True)
class RuntimeSteps:
    """Injected domain operations, in the order required by TASK.md 2.1.

    Required stages are perception, L0, trigger, conditional L1, state,
    decision, expression and result feedback. Optional background stages run
    after foreground completion and never prevent the next tick.
    """
    perceive: Callable[[], Any]
    append_l0: Callable[[Any], str | None]
    should_trigger_l1: Callable[[Any, str | None], bool]
    generate_l1: Callable[[Any, str | None], Any]
    update_state: Callable[[Any, Any], Any]
    decide: Callable[[Any, Any], Any]
    express: Callable[[Any, Any], Any]
    feed_result: Callable[[Any, Any, Any], Any]
    sleep_consolidation: Callable[[Any], Any] | None = None
    reflection_calibration: Callable[[Any], Any] | None = None
    retrieval_bias_update: Callable[[Any], Any] | None = None
    should_process: Callable[[Any], str | None] | None = None


class RuntimePipeline:
    """Execute the role-scoped CetherYH main loop with observable stage results."""

    def __init__(
        self,
        *,
        role_scope: str,
        scope_guard: ScopeGuard,
        steps: RuntimeSteps,
        config: RuntimeConfig = RuntimeConfig(),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        event_sink: Callable[[RuntimeEvent], None] | None = None,
    ) -> None:
        if not role_scope:
            raise ValueError("role_scope must be non-empty")
        self.role_scope = role_scope
        self._scope_guard = scope_guard
        self._steps = steps
        self.config = config
        self._clock = clock
        self._event_sink = event_sink or (lambda _event: None)
        self._stop_requested = False
        self._tick_id = 0
        self._events: list[RuntimeEvent] = []
        self._stage_active = False
        self._lifecycle_lock = threading.Lock()
        self._stage_lock = threading.Lock()
        self._stage_idle = threading.Event()
        self._stage_idle.set()
        self._stage_thread: threading.Thread | None = None
        self._was_sleeping = False

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def stop(self) -> None:
        """Request cancellation; the current synchronous stage finishes, later ticks stop."""
        with self._lifecycle_lock:
            self._stop_requested = True

    def cancel(self, timeout: float | None = None) -> bool:
        """Stop scheduling work and wait for the active synchronous tick to finish."""
        self.stop()
        with self._lifecycle_lock:
            current_tick_thread = self._stage_active and threading.current_thread() is self._stage_thread
        if current_tick_thread:
            return False
        return self._stage_idle.wait(timeout)

    def tick(self) -> RuntimeContext:
        """Run one complete foreground tick, then best-effort background stages."""
        with self._lifecycle_lock:
            if self._stop_requested:
                raise RuntimeError("runtime is stopping")
        if not self._stage_lock.acquire(blocking=False):
            raise RuntimeError("concurrent runtime ticks are forbidden")
        with self._lifecycle_lock:
            if self._stop_requested:
                self._stage_lock.release()
                raise RuntimeError("runtime is stopping")
            self._stage_active = True
            self._stage_thread = threading.current_thread()
            self._stage_idle.clear()
        self._tick_id += 1
        context = RuntimeContext(self._tick_id, self.role_scope, self._clock())
        try:
            self._scope_guard.ensure_role_scope(self.role_scope)
            context = self._foreground(context)
            context = self._background(context)
            return context
        finally:
            with self._lifecycle_lock:
                self._stage_active = False
                self._stage_thread = None
                self._stage_idle.set()
            self._stage_lock.release()

    def run(
        self,
        *,
        should_stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_ticks: int | None = None,
    ) -> RuntimeReport:
        """Run until stopped or ``max_ticks``; sleep only between ticks."""
        if max_ticks is not None and max_ticks < 0:
            raise ValueError("max_ticks must be non-negative")
        completed = 0
        last: RuntimeContext | None = None
        reason = "stop_requested"
        while not self._stop_requested and not (should_stop and should_stop()):
            if max_ticks is not None and completed >= max_ticks:
                reason = "max_ticks"
                break
            last = self.tick()
            completed += 1
            if not self._stop_requested and (max_ticks is None or completed < max_ticks):
                sleep(self.config.interval_seconds)
        if should_stop and should_stop():
            reason = "external_stop"
        return RuntimeReport(completed, tuple(self._events), last, reason)

    def _foreground(self, context: RuntimeContext) -> RuntimeContext:
        perception = self._run_stage(context, "perception", lambda: self._steps.perceive())
        if getattr(perception, "sleeping", False) or (isinstance(perception, dict) and perception.get("sleeping")):
            self._was_sleeping = True
            self._emit(context, "sleep", "frozen", "sleep state freezes perception and foreground state evolution")
            return _replace_context(context, perception=perception)
        if self._was_sleeping:
            self._was_sleeping = False
            self._emit(context, "sleep", "wake", "sleep interval ended")
        context = _replace_context(context, perception=perception)
        if self._steps.should_process is not None:
            reason = self._run_stage(context, "gate", lambda: self._steps.should_process(perception))
            if reason:
                self._emit(context, "gate", "blocked", str(reason))
                return context
        l0_id = self._run_stage(context, "l0", lambda: self._steps.append_l0(perception))
        unchanged = l0_id is None and _event_value(perception, "changed", True) is False
        context = _replace_context(context, l0_id=l0_id)
        triggered = False if unchanged else self._run_stage(
            context, "trigger", lambda: self._steps.should_trigger_l1(perception, l0_id)
        )
        context = _replace_context(context, trigger=bool(triggered))
        if triggered:
            narrative = self._run_stage(context, "l1", lambda: self._steps.generate_l1(perception, l0_id))
            context = _replace_context(context, narrative=narrative)
        state = self._run_stage(context, "state", lambda: self._steps.update_state(perception, context.narrative))
        context = _replace_context(context, state=state)
        if unchanged:
            self._emit(context, "runtime", "skipped", "observation unchanged; state updated")
            return context
        decision = self._run_stage(context, "decision", lambda: self._steps.decide(context, state))
        context = _replace_context(context, decision=decision)
        expression = self._run_stage(context, "expression", lambda: self._steps.express(context, decision))
        context = _replace_context(context, expression=expression)
        result = self._run_stage(context, "result_feedback", lambda: self._steps.feed_result(context, expression, state))
        return _replace_context(context, result=result)

    def _background(self, context: RuntimeContext) -> RuntimeContext:
        outputs = dict(context.background_results)
        mode = getattr(context.perception, "sleep_mode", None)
        if isinstance(context.perception, dict):
            mode = context.perception.get("sleep_mode", mode)
        if mode not in {"light", "deep"}:
            return context
        operations = [("sleep_consolidation", self._steps.sleep_consolidation)]
        if mode == "deep":
            operations.extend((
                ("reflection_calibration", self._steps.reflection_calibration),
                ("retrieval_bias_update", self._steps.retrieval_bias_update),
            ))
        for name, operation in operations:
            if operation is None:
                continue
            try:
                outputs[name] = self._run_stage(context, name, lambda op=operation: op(context))
            except Exception as exc:
                if not self.config.background_failures_are_non_blocking:
                    raise
                outputs[name] = None
                self._emit(context, name, "error", str(exc))
        return _replace_context(context, background_results=outputs)

    def _run_stage(self, context: RuntimeContext, stage: str, operation: Callable[[], Any]) -> Any:
        try:
            self._scope_guard.ensure_role_scope(self.role_scope)
            result = operation()
        except Exception as exc:
            self._emit(context, stage, "error", str(exc))
            raise
        self._emit(context, stage, "completed")
        return result

    def _emit(self, context: RuntimeContext, stage: str, status: str, detail: str = "") -> None:
        event = RuntimeEvent(context.tick_id, stage, status, self.role_scope, self._clock(), detail)
        self._events.append(event)
        self._event_sink(event)


def _event_value(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _replace_context(context: RuntimeContext, **changes: Any) -> RuntimeContext:
    values = {field_name: getattr(context, field_name) for field_name in RuntimeContext.__dataclass_fields__}
    values.update(changes)
    return RuntimeContext(**values)


def run_loop(
    perceiver: Perceiver,
    interval_seconds: float,
    should_stop: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    max_ticks: int | None = None,
) -> int:
    """Compatibility loop for perception-only clients; returns tick count."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    ticks = 0
    while not should_stop():
        if max_ticks is not None and ticks >= max_ticks:
            break
        perceiver.tick()
        ticks += 1
        sleep(interval_seconds)
    return ticks
