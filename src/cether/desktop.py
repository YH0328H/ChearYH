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
from .diary import DiaryService
from .events import RuntimeEvents
from .memory_lifecycle import MemoryLifecycleService
from .mode import ModeController
from .perception import Perceiver
from .perception_config import load_perception_config
from .providers import LocalRuleProvider, OpenAICompatibleProvider, load_provider_config
from .sensing import FirstRunNotice, list_seen
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
        self._capture_paused = False
        self._events_paused = False
        self._perceiver: Perceiver | None = None
        self._events: RuntimeEvents | None = None
        self._first_run_notice: FirstRunNotice | None = None
        self._lifecycle: MemoryLifecycleService | None = None
        self._diary: DiaryService | None = None
        self._seen_path: Path | None = None
        self._mode = ModeController()
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
        if action == "role_archive":
            role_id = str(request["role_id"])
            archived = self.registry.archive(role_id)
            return {"role_id": archived.role_id, "archived": archived.archived}
        if action == "role_restore":
            restored = self.registry.restore(str(request["role_id"]))
            return {"role_id": restored.role_id, "archived": restored.archived}
        if action == "role_delete":
            self.registry.delete_archived(str(request["role_id"]), confirmations=int(request.get("confirmations", 0)))
            return {"deleted": True, "role_id": str(request["role_id"])}
        if action == "role_export":
            destination = Path(str(request["destination"])).expanduser().resolve()
            result = self.registry.export_package(str(request["role_id"]), destination)
            return {"package": str(result)}
        if action == "role_import":
            package = Path(str(request["package"])).expanduser().resolve()
            workspace = Path(str(request["workspace"])).expanduser().resolve()
            cfg = self.registry.import_package(package, workspace, conflict=str(request.get("conflict", "rename")),
                                               renamed_to=request.get("renamed_to"))
            return {"role_id": cfg.role_id, "name": cfg.name, "wake_pending": bool(self.registry.pending_wake(cfg.role_id))}
        if action == "set_mode":
            state = self._mode.set_override(request.get("mode"))
            return {"mode": state.mode, "source": state.source, "override": state.override}
        if action == "complete_onboarding":
            if self.registry.active:
                path = self.registry.active.workspace / "onboarding.json"
                path.write_text(json.dumps({"completed": True}, ensure_ascii=False), encoding="utf-8")
            return self._bootstrap()
        if action == "tool_notice":
            if self._events:
                self._events.record(str(request.get("kind", "tool")), str(request.get("description", "")))
            return {"visible": True, "status": "recorded"}
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
            self._perceiver = None
            self._events = None
            self._lifecycle = None
            self._diary = None
            return
        if self.runtime:
            self.runtime.close()
        self._lifecycle = MemoryLifecycleService(role, self.registry)
        self._diary = DiaryService(role, self.registry)
        self._seen_path = role.workspace / "world.jsonl"
        self._first_run_notice = FirstRunNotice(role.workspace / "sensing-consent.json")
        self._perception_config = load_perception_config(Path(__file__).resolve().parents[2] / "config" / "perception.toml")
        self._perceiver = self._build_perceiver(role)
        self._events = RuntimeEvents(role.workspace / "runtime-events.jsonl")
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
            perceive=self._perceive, decision=decision_provider.decide,
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
        self.conversation = ConversationService(
            role=role, registry=self.registry, runtime=self.runtime, provider=provider,
            injected_memories=self._consume_injections,
            excluded_ids=lambda: self._lifecycle.excluded_ids() if self._lifecycle else frozenset(),
        )
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
            forget_memory=self._forget_memory,
            restore_memory=self._restore_memory,
            seen_records=self._seen_records,
            diary_page=self._diary_page,
            delete_diary=self._delete_diary,
            acknowledge_perception=self._acknowledge_perception,
            perception_paused=lambda: self._capture_paused,
            events_paused=lambda: self._events_paused,
            first_run_notice_due=self._first_run_notice_due,
            memory_available=lambda: True,
        )

    def _build_perceiver(self, role: RoleContext) -> Perceiver:
        """Build default-on screen perception; unavailable Windows capture degrades to a stable tick."""
        try:
            from .capture import foreground_app, grab_primary_monitor
            from .vision import describe, load_vision_config
            vision_path = Path(__file__).resolve().parents[2] / "config" / "vision.toml"
            cfg = load_vision_config(vision_path, os.environ) if vision_path.is_file() else None
            describer = (lambda: describe(cfg, self._last_png, _post_json)) if cfg and cfg.api_key else None
            self._last_png = b""
            def capture():
                thumb, png = grab_primary_monitor()
                self._last_png = png
                return thumb
            return Perceiver(capture, describer, role.workspace / "world.jsonl", foreground_app,
                              allow_apps=self._perception_config.allow_apps,
                              deny_apps=self._perception_config.deny_apps,
                              hamming_threshold=self._perception_config.hamming_threshold)
        except Exception:
            return Perceiver(lambda: [0] * 64, None, role.workspace / "world.jsonl", lambda: "",
                              allow_apps=self._perception_config.allow_apps,
                              deny_apps=self._perception_config.deny_apps,
                              hamming_threshold=self._perception_config.hamming_threshold)

    def _perceive(self) -> Any:
        if self._first_run_notice_due():
            return {"changed": False, "description": "首次感知说明待确认", "perception_consent_required": True}
        if self._perceiver is None:
            return {"changed": False, "description": "感知通道未配置"}
        try:
            tick = self._perceiver.tick()
        except Exception as exc:
            if self._events:
                self._events.record("perception_error", str(exc))
            return {"changed": False, "description": "感知暂不可用", "error": str(exc)}
        if not tick.changed:
            return {"changed": False, "description": None, "distance": tick.distance}
        return {"changed": True, "description": tick.description or "屏幕发生变化（尚未配置视觉描述）", "distance": tick.distance,
                "source": "perception", "foreground_app": self._foreground_app()}

    def _foreground_app(self) -> str:
        try:
            from .capture import foreground_app
            return foreground_app()
        except (ImportError, OSError, AttributeError):
            return ""

    def _first_run_notice_due(self) -> bool:
        return bool(self._first_run_notice and self._first_run_notice.due())

    def _acknowledge_perception(self) -> bool:
        if not self._first_run_notice:
            raise RuntimeError("perception consent unavailable")
        self._first_run_notice.mark_shown()
        return True

    def _seen_records(self) -> list[dict[str, Any]]:
        if not self._seen_path or not self._seen_path.exists():
            return []
        return [json.loads(line) for line in self._seen_path.read_text(encoding="utf-8").splitlines() if line.strip()][-50:]

    def _forget_memory(self, memory_id: str, choice: str) -> dict[str, Any]:
        if not self._lifecycle:
            raise RuntimeError("memory lifecycle unavailable")
        return asdict(self._lifecycle.forget(memory_id, choice))

    def _restore_memory(self, memory_id: str, choice: str) -> dict[str, Any]:
        if not self._lifecycle:
            raise RuntimeError("memory lifecycle unavailable")
        return asdict(self._lifecycle.restore(memory_id, choice))

    def _consume_injections(self) -> tuple[dict, ...]:
        return self._lifecycle.consume_injections() if self._lifecycle else ()

    def _diary_page(self) -> list[dict[str, Any]]:
        return self._diary.list_entries() if self._diary else []

    def _delete_diary(self, diary_id: str) -> bool:
        if not self._diary:
            raise RuntimeError("diary unavailable")
        return self._diary.delete(diary_id)

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
        mode = self._mode.state(self._foreground_app())
        return StatusView(translate_to_texture("social_battery", battery), reason, tuple(self._read_mind_box()),
                          "未配置主动窗口", sleep_status, mode.mode, mode.source)

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
        if self._lifecycle:
            records = [self._lifecycle.annotate(record) for record in records]
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
        if self._perceiver:
            self._perceiver.pause_capture() if value else self._perceiver.resume_capture()

    def _set_events_paused(self, value: bool) -> None:
        self._events_paused = value
        if self._events:
            self._events.pause() if value else self._events.resume()

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
