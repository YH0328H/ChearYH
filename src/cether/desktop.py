"""JSON-lines bridge used by the Tauri desktop shell."""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .conversation import ConversationService
from .cognition import LocalDecisionProvider, LocalExpressionProvider, load_cognition_config
from .graph_retrieval import LocalCooccurrenceGraphProvider
from .l0 import L0Archive
from .providers import LocalRuleProvider, OpenAICompatibleProvider, load_provider_config
from .retrieval import embed_texts, load_embedding_config
from .roles import RoleContext, RoleRegistry
from .runtime_services import RuntimeServices
from .sleep import SleepService, load_sleep_config
from .sleep_schedule import SleepSchedule, load_sleep_schedule_config
from .spatial_retrieval import SpatialMemoryProvider
from .trigger import TriggerConfig
from .ui_contract import RoleCardView, StatusView, UiContract
from .state import translate_to_texture


class DesktopRuntime:
    """Own the active role and expose a stable desktop-facing action surface."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.registry = RoleRegistry(data_dir / "roles.json")
        if not self.registry.list_roles():
            role = self.registry.create_role("默认角色", data_dir / "roles" / "default")
            self.registry.switch(role.role_id)
        elif self.registry.active is None:
            self.registry.switch(self.registry.list_roles()[0].role_id)
        self.runtime: RuntimeServices | None = None
        self.conversation: ConversationService | None = None
        self._capture_paused = False
        self._events_paused = False
        self._ui_notices: list[str] = []
        self.ui: UiContract | None = None
        self._bind_active()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "bootstrap":
            return self._bootstrap()
        if action == "create_role":
            name = str(request.get("name", "")).strip()
            if not name:
                raise ValueError("role name must not be empty")
            role_id = os.urandom(8).hex()
            role = self.registry.create_role(name, self.data_dir / "roles" / role_id, role_id=role_id)
            self.registry.switch(role.role_id)
            self._bind_active()
            return self._bootstrap()
        if action == "switch_role":
            return self._switch_role(str(request["role_id"]))
        if action == "send_message":
            if self.conversation is None:
                raise RuntimeError("no active conversation")
            turn = self.conversation.send(str(request.get("text", "")))
            return {"turn": asdict(turn), "history": self.conversation.history()}
        if action == "ui_action":
            if self.ui is None:
                raise RuntimeError("desktop UI contract is unavailable")
            result = self.ui.dispatch(str(request["ui_action"]), dict(request.get("payload") or {}))
            return {"accepted": result.accepted, "feedback": result.feedback.to_dict(), "payload": result.payload,
                    "view": self._view_payload()}
        if action == "memory_timeline":
            if self.ui is None:
                raise RuntimeError("desktop UI contract is unavailable")
            page = self.ui.memory_timeline(request.get("cursor"), int(request.get("limit", 100)))
            return asdict(page)
        if action == "shutdown":
            if self.runtime:
                self.runtime.close()
                self.runtime = None
                self.conversation = None
            return {"stopped": True}
        raise ValueError(f"unknown action: {action}")

    def _bootstrap(self) -> dict[str, Any]:
        return {
            "active_role": self._role_view(self.registry.active, active=True),
            "roles": [self._role_view(_context(r), active=r.role_id == self.registry.active.config.role_id if self.registry.active else False)
                      for r in self.registry.list_roles()],
            "history": self.conversation.history() if self.conversation else [],
            "view": self._view_payload(),
        }

    def _switch_role(self, role_id: str) -> dict[str, Any]:
        result = self.registry.switch(role_id)
        if result.error:
            raise RuntimeError(result.error)
        self._bind_active()
        payload = self._bootstrap()
        payload["switch_progress"] = [asdict(item) for item in result.progress]
        payload["wake_pending"] = bool(result.wake)
        return payload

    def _bind_active(self) -> None:
        role = self.registry.active
        if role is None:
            self.runtime = None
            self.conversation = None
            self.ui = None
            return
        if self.runtime:
            self.runtime.close()
        cognition_path = Path(__file__).resolve().parents[2] / "config" / "cognition.toml"
        decision_config, expression_config = load_cognition_config(cognition_path)
        decision_provider = LocalDecisionProvider(decision_config)
        expression_provider = LocalExpressionProvider(expression_config)
        sleep_config_path = Path(__file__).resolve().parents[2] / "config" / "sleep.toml"
        sleep_service = SleepService(role, self.registry, config=load_sleep_config(sleep_config_path))
        sleep_schedule = SleepSchedule(load_sleep_schedule_config(sleep_config_path))
        spatial_provider = SpatialMemoryProvider(role, self.registry)
        graph_provider = LocalCooccurrenceGraphProvider(role, self.registry)
        embedding_path = Path(__file__).resolve().parents[2] / "config" / "embedding.toml"
        embedding_config = load_embedding_config(embedding_path, os.environ) if embedding_path.is_file() else None

        def embedding_provider(texts: list[str]) -> list[list[float]]:
            if embedding_config is None or not embedding_config.api_key:
                return []
            return embed_texts(embedding_config, texts, _post_json)

        self.runtime = RuntimeServices(
            role=role, registry=self.registry, trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: None, decision=decision_provider.decide,
            expression=lambda decision, request: expression_provider.express(decision, request),
            sleep_consolidation=sleep_service.consolidate,
            reflection=lambda active_role, state: {
                **sleep_service.reflect(active_role, state),
                **sleep_service.deep_sleep(active_role, state),
            },
            retrieval_index_update=lambda active_role: sleep_service.refresh_retrieval_bias(
                active_role, self.runtime._read_state()),
            spatial_provider=spatial_provider,
            embedding_provider=embedding_provider if embedding_config and embedding_config.api_key else None,
            graph_provider=graph_provider,
            sleep_mode=lambda active_role, now: sleep_schedule(now),
        )
        provider = LocalRuleProvider()
        config_path = Path(os.environ.get("CETHER_CHAT_CONFIG", self.data_dir / "chat.toml"))
        if config_path.is_file():
            config = load_provider_config(config_path)
            if config.api_key():
                provider = OpenAICompatibleProvider(config)
        self.conversation = ConversationService(role=role, registry=self.registry, runtime=self.runtime, provider=provider)
        self.ui = self._build_ui_contract(role)

    def _build_ui_contract(self, role: RoleContext) -> UiContract:
        return UiContract(
            role_cards=self._role_cards,
            status=self._status_view,
            look_now=self._look_now,
            set_capture_paused=self._set_capture_paused,
            set_events_paused=self._set_events_paused,
            remember_this=self._remember_this,
            memory_page=self._memory_page,
            perception_paused=lambda: self._capture_paused,
            events_paused=lambda: self._events_paused,
            memory_available=lambda: True,
        )

    def _role_cards(self) -> tuple[RoleCardView | None, list[RoleCardView]]:
        active_id = self.registry.active.config.role_id if self.registry.active else None
        cards = [self._card(_context(config), config.role_id == active_id) for config in self.registry.list_roles(include_archived=True)]
        active = next((card for card in cards if card.active), None)
        return active, cards

    def _card(self, role: RoleContext, active: bool) -> RoleCardView:
        return RoleCardView(role.config.role_id, role.config.name, active, role.config.archived,
                            role.config.metadata.get("last_active"), self._status_summary(role),
                            str(role.workspace), role.config.self_awareness)

    def _status_summary(self, role: RoleContext) -> str:
        if self.registry.active and self.registry.active.scope_id == role.scope_id and self.runtime:
            state = self.runtime._read_state()
            return translate_to_texture("social_battery", float(state.get("social_battery", 0.8)))
        return "休眠中"

    def _status_view(self) -> StatusView:
        state = self.runtime._read_state() if self.runtime else {}
        battery = float(state.get("social_battery", 0.8))
        sleep_mode = self.runtime._sleep_mode if self.runtime else "awake"
        if sleep_mode in {"light", "deep"}:
            sleep_status = "深睡中" if sleep_mode == "deep" else "浅睡中"
        else:
            sleep_status = "清醒"
        reason = self.runtime._last_gate_reason if self.runtime else None
        return StatusView(translate_to_texture("social_battery", battery), reason, tuple(self._read_mind_box()),
                          "未配置主动窗口", sleep_status, "companion", "runtime")

    def _read_mind_box(self) -> list[str]:
        path = self.registry.active.workspace / "mind_box.json" if self.registry.active else None
        if not path or not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw][-5:]
        except (OSError, ValueError, TypeError):
            return []

    def _memory_page(self, cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None, int]:
        del cursor
        if not self.registry.active:
            return [], None, 0
        records = list(L0Archive(self.registry.active.workspace / "memory" / "l0.jsonl"))
        records.reverse()
        page = records[:limit]
        return page, None, len(records)

    def _look_now(self) -> dict[str, Any]:
        if self.runtime is None:
            return {"changed": False, "description": "当前没有活跃角色"}
        event = self.runtime.perception_provider()
        if event is None:
            return {"changed": False, "description": "当前感知通道未配置"}
        return event if isinstance(event, dict) else {"changed": True, "description": str(event)}

    def _remember_this(self, text: str) -> str:
        if not text.strip() or not self.runtime:
            raise ValueError("memory text must not be empty")
        return self.runtime._l0.append(text.strip(), "manual", metadata={"manual_mark": True, "memory_tier": "high"})

    def _set_capture_paused(self, value: bool) -> None:
        self._capture_paused = value

    def _set_events_paused(self, value: bool) -> None:
        self._events_paused = value

    def _view_payload(self) -> dict[str, Any]:
        if self.ui is None:
            return {}
        # Round-trip through JSON so tuple-backed dataclass fields match the bridge payload shape.
        return json.loads(json.dumps(asdict(self.ui.app_view()), ensure_ascii=False))

    @staticmethod
    def _role_view(context, *, active: bool = False) -> dict[str, Any] | None:
        if context is None:
            return None
        return {"role_id": context.config.role_id, "name": context.config.name,
                "active": active, "self_awareness": context.config.self_awareness}


def _context(config):
    return RoleContext(config, config.role_id)


def _post_json(url: str, body: dict, headers: dict) -> dict:
    """POST JSON to an OpenAI-compatible embedding endpoint."""
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=45.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    data_dir = Path(sys.argv[1]).expanduser().resolve()
    runtime = DesktopRuntime(data_dir)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = runtime.handle(request)
            output = {"id": request.get("id"), "ok": True, "result": result}
        except Exception as exc:
            output = {"id": request.get("id") if isinstance(request, dict) else None,
                      "ok": False, "error": str(exc), "type": type(exc).__name__}
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
