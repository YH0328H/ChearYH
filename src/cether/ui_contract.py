"""Backend-facing UI view models and action results for TASK.md chapter 10.

The Tauri shell owns rendering and animation. This module defines stable,
serializable data and command semantics so UI code does not reach into storage
or infer role state. Actions are synchronous domain operations; callers should
run long-running providers asynchronously outside this contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class UiAction(str, Enum):
    LOOK_NOW = "look_now"
    PAUSE_CAPTURE = "pause_capture"
    PAUSE_RUNTIME_EVENTS = "pause_runtime_events"
    OPEN_MEMORIES = "open_memories"
    REMEMBER_THIS = "remember_this"
    THINK_AGAIN = "think_again"
    DEEPEN = "deepen"
    SWITCH_ROLE = "switch_role"
    ARCHIVE_MEMORY = "archive_memory"
    RESTORE_MEMORY = "restore_memory"
    INJECT_ONCE = "inject_once"


@dataclass(frozen=True)
class UiFeedback:
    action: str
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoleCardView:
    role_id: str
    name: str
    active: bool
    archived: bool
    last_active: str | None
    status_summary: str
    workspace: str
    self_awareness: str


@dataclass(frozen=True)
class StatusView:
    texture: str
    gate_reason: str | None
    mind_box: tuple[str, ...]
    window_status: str
    sleep_status: str
    mode: str
    mode_source: str


@dataclass(frozen=True)
class MemoryNodeView:
    memory_id: str
    text: str
    category: str
    weight: float
    x: float
    y: float
    timestamp: str
    archived: bool = False
    connections: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class MemoryTimelineView:
    records: tuple[dict[str, Any], ...]
    next_cursor: str | None
    total: int


@dataclass(frozen=True)
class AppView:
    active_role: RoleCardView | None
    roles: tuple[RoleCardView, ...]
    status: StatusView | None
    perception_paused: bool
    events_paused: bool
    first_run_notice_due: bool
    backend_memory_available: bool
    inline_notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserActionResult:
    accepted: bool
    feedback: UiFeedback
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NavigationItem:
    key: str
    label: str
    visible: bool = True


MAIN_NAVIGATION: tuple[NavigationItem, ...] = (
    NavigationItem("companion", "陪伴"),
    NavigationItem("conversation", "会话"),
    NavigationItem("memory_starfield", "记忆星空"),
    NavigationItem("memory_timeline", "冷库时间轴"),
    NavigationItem("roles", "角色"),
    NavigationItem("settings", "配置"),
)

CONTEXT_MENU_ACTIONS: tuple[UiAction, ...] = (
    UiAction.LOOK_NOW,
    UiAction.PAUSE_CAPTURE,
    UiAction.OPEN_MEMORIES,
    UiAction.REMEMBER_THIS,
)

ROLE_AREA_ACTIONS: tuple[UiAction, ...] = (UiAction.SWITCH_ROLE,)


class UiContract:
    """Serialize current product state and validate UI-originated commands.

    Dependencies are injected callbacks, keeping this contract independent
    from a specific database, Tauri IPC layer, or model provider.
    """

    def __init__(
        self,
        *,
        role_cards: Callable[[], tuple[RoleCardView | None, list[RoleCardView]]],
        status: Callable[[], StatusView | None],
        look_now: Callable[[], Any] | None = None,
        set_capture_paused: Callable[[bool], None] | None = None,
        set_events_paused: Callable[[bool], None] | None = None,
        remember_this: Callable[[str], Any] | None = None,
        think_again: Callable[[str], bool] | None = None,
        deepen: Callable[[str], float] | None = None,
        switch_role: Callable[[str], Any] | None = None,
        memory_page: Callable[[str | None, int], tuple[list[dict[str, Any]], str | None, int]] | None = None,
        perception_paused: Callable[[], bool] = lambda: False,
        events_paused: Callable[[], bool] = lambda: False,
        first_run_notice_due: Callable[[], bool] = lambda: False,
        memory_available: Callable[[], bool] = lambda: True,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._role_cards = role_cards
        self._status = status
        self._actions = {
            UiAction.LOOK_NOW: look_now,
            UiAction.REMEMBER_THIS: remember_this,
            UiAction.THINK_AGAIN: think_again,
            UiAction.DEEPEN: deepen,
            UiAction.SWITCH_ROLE: switch_role,
        }
        self._set_capture_paused = set_capture_paused or (lambda _value: None)
        self._set_events_paused = set_events_paused or (lambda _value: None)
        self._memory_page = memory_page or (lambda _cursor, _limit: ([], None, 0))
        self._perception_paused = perception_paused
        self._events_paused = events_paused
        self._first_run_notice_due = first_run_notice_due
        self._memory_available = memory_available
        self._clock = clock
        self._capture_paused = perception_paused()
        self._runtime_events_paused = events_paused()
        self._notices: list[str] = []

    def app_view(self) -> AppView:
        active, roles = self._role_cards()
        return AppView(
            active_role=active,
            roles=tuple(roles),
            status=self._status(),
            perception_paused=self._capture_paused,
            events_paused=self._runtime_events_paused,
            first_run_notice_due=self._first_run_notice_due(),
            backend_memory_available=self._memory_available(),
            inline_notices=tuple(self._notices),
        )

    def memory_timeline(self, cursor: str | None = None, limit: int = 100) -> MemoryTimelineView:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        records, next_cursor, total = self._memory_page(cursor, limit)
        return MemoryTimelineView(tuple(records), next_cursor, total)

    def dispatch(self, action: UiAction | str, payload: dict[str, Any] | None = None) -> UserActionResult:
        """Execute a UI action and return explicit, user-visible feedback."""
        action = UiAction(action)
        data = payload or {}
        if action == UiAction.PAUSE_CAPTURE:
            value = bool(data["paused"])
            self._set_capture_paused(value)
            self._capture_paused = value
            return self._result(action, "updated", "截屏感知已暂停" if value else "截屏感知已恢复", {"paused": value})
        if action == UiAction.PAUSE_RUNTIME_EVENTS:
            value = bool(data["paused"])
            self._set_events_paused(value)
            self._runtime_events_paused = value
            return self._result(action, "updated", "运行事件感知已暂停" if value else "运行事件感知已恢复", {"paused": value})
        if action in {UiAction.OPEN_MEMORIES}:
            return self._result(action, "opened", "已打开记忆面板")
        if action == UiAction.ARCHIVE_MEMORY:
            choice = data.get("choice")
            if choice is None:
                return self._result(action, "opened", "请选择遗忘方式", {"memory_id": data["memory_id"], "choices": ["delete", "decrease_weight", "move_to_cold"], "delete_warning": "不推荐，会造成记忆断层"})
            if choice not in {"delete", "decrease_weight", "move_to_cold"}:
                raise ValueError("unknown forget choice")
            return self._result(action, "accepted", "已记录记忆处理请求", {"memory_id": data["memory_id"], "choice": choice, "l0_immutable": True})
        if action == UiAction.RESTORE_MEMORY:
            choice = data.get("choice")
            if choice is None:
                return self._result(action, "opened", "请选择捞回方式", {"memory_id": data["memory_id"], "choices": ["boost", "move_to_hot", "inject_once"]})
            if choice not in {"boost", "move_to_hot", "inject_once"}:
                raise ValueError("unknown restore choice")
            return self._result(action, "accepted", "已记录冷库捞回请求", {"memory_id": data["memory_id"], "choice": choice, "storage_unchanged": choice == "inject_once"})
        if action == UiAction.LOOK_NOW and self._capture_paused:
            return self._result(action, "blocked", "截屏感知已暂停", accepted=False)
        callback = self._actions[action]
        if callback is None:
            return self._result(action, "unavailable", "当前功能暂不可用", accepted=False)
        try:
            result = callback(**self._callback_args(action, data))
        except Exception as exc:
            self._notices.append(str(exc))
            return self._result(action, "error", str(exc), accepted=False)
        if action == UiAction.REMEMBER_THIS:
            return self._result(action, "submitted", "已提交", {"result": result})
        if action == UiAction.THINK_AGAIN:
            changed = bool(result)
            return self._result(action, "completed", "想过了" if changed else "暂时没变", {"changed": changed})
        if action == UiAction.DEEPEN:
            return self._result(action, "updated", "记忆权重已提升", {"weight": result})
        if action == UiAction.SWITCH_ROLE:
            if getattr(result, "error", None):
                return self._result(action, "error", result.error, {"active_role_id": result.active_role_id}, accepted=False)
            return self._result(action, "completed", "角色已切换", {"active_role_id": getattr(result, "active_role_id", result)})
        return self._result(action, "completed", "已看一眼", {"result": result})

    @staticmethod
    def _callback_args(action: UiAction, data: dict[str, Any]) -> dict[str, Any]:
        if action == UiAction.LOOK_NOW:
            return {}
        if action == UiAction.SWITCH_ROLE:
            return {"role_id": data["role_id"]}
        if action == UiAction.REMEMBER_THIS:
            return {"text": data["text"]}
        return {"memory_id": data["memory_id"]}

    def _result(self, action: UiAction, status: str, message: str, data: dict[str, Any] | None = None, *, accepted: bool = True) -> UserActionResult:
        feedback = UiFeedback(action.value, status, message, data or {}, self._clock().isoformat())
        return UserActionResult(accepted, feedback, data or {})


def memory_starfield(nodes: list[dict[str, Any]], *, width: float = 1000, height: float = 700) -> tuple[MemoryNodeView, ...]:
    """Project indexed memory nodes into deterministic starfield view models.

    Spatial coordinates come from stable room/slot ids. Weight controls size
    and brightness; category is retained for color mapping by the renderer.
    """
    if width <= 0 or height <= 0:
        raise ValueError("canvas dimensions must be positive")
    result: list[MemoryNodeView] = []
    for node in nodes:
        room = int(node.get("room", 0))
        slot = int(node.get("slot_id", 0))
        capacity = max(1, int(node.get("room_capacity", 50)))
        weight = max(0.0, min(1.0, float(node.get("weight", 0.0))))
        x = ((room + 0.5) / (room + 1.0)) * width
        y = ((slot + 0.5) / capacity) * height
        result.append(MemoryNodeView(
            memory_id=str(node["memory_id"]), text=str(node.get("text", "")),
            category=str(node.get("category", "fact")), weight=weight,
            x=x, y=y, timestamp=str(node.get("timestamp", "")),
            archived=bool(node.get("archived", False)),
            connections=tuple((str(k), float(v)) for k, v in node.get("connections", [])),
        ))
    return tuple(result)
