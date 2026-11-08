"""JSON-lines bridge used by the Tauri desktop shell."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import traceback
import urllib.request
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import random
import threading
import time

from .checkpoint import MindBox, Outcome, run_checkpoint
from .window import checkpoint_block_reason, load_window_config, next_fixed_interval, next_random_interval
from .context_budget import ContextSegment, allocate_budget, load_budget_config
from pathlib import Path
from typing import Any

from .conversation import ConversationService
from .memory_retrieval import RetrievalConfigWatcher
from .spatial import SpatialIndex
from .cognition import LocalDecisionProvider, LocalExpressionProvider, load_cognition_config
from .graph_retrieval import LocalCooccurrenceGraphProvider
from .l0 import L0Archive
from .diary import DiaryService
from .events import RuntimeEvents
from .presets import register_presets
from .ui_contract import memory_starfield
import tomllib
from .memory_lifecycle import MemoryLifecycleService
from .mode import ModeController
from .perception import Perceiver
from .perception_config import load_perception_config
from .providers import LocalRuleProvider, OpenAICompatibleProvider, load_provider_config
from .sensing import FirstRunNotice, list_seen
from .retrieval import embed_texts, load_embedding_config
from .memory_retrieval import tokenize
from .roles import RoleContext, RoleRegistry
from .runtime_services import RuntimeServices
from .sleep import SleepService, load_sleep_config
from .sleep_schedule import SleepSchedule, load_sleep_schedule_config
from .skills import SkillRegistry
from .spatial_retrieval import SpatialMemoryProvider
from .trigger import TriggerConfig
from .ui_contract import RoleCardView, StatusView, UiContract
from .state import translate_to_texture


class DesktopRuntime:
    """Own the active role and expose a stable desktop-facing action surface."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        project_root = Path(__file__).resolve().parents[2]
        resource_root = Path(os.environ.get("CETHER_RESOURCE_DIR", project_root)).expanduser().resolve()
        self.config_dir = data_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        bundled_config = resource_root / "config"
        for bundled_file in bundled_config.glob("*.toml"):
            target = self.config_dir / bundled_file.name
            if not target.exists():
                target.write_bytes(bundled_file.read_bytes())
        preset_source = resource_root / "presets"
        if preset_source.is_dir():
            register_presets(preset_source, data_dir / "presets", data_dir / "presets-manifest.json")
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
        self.skills = SkillRegistry()
        self.ui: UiContract | None = None
        self._pipeline_thread: threading.Thread | None = None
        self._pipeline_stop = threading.Event()
        self._snapshot_stop = threading.Event()
        self._snapshot_thread: threading.Thread | None = None
        self._snapshot_turns = 0
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._scheduler_rng = random.Random()
        self._next_checkpoint_at = time.monotonic()
        self._missed_checkpoints = 0
        self._hourly_fires: list[datetime] = []
        self._last_snapshot_at = time.monotonic()
        self._snapshot_lock = threading.Lock()
        self._bind_active()
        self._start_snapshot_worker()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "bootstrap":
            return self._bootstrap()
        if action == "create_role":
            name = str(request.get("name", "")).strip()
            if not name:
                raise ValueError("role name must not be empty")
            preset_id = str(request.get("preset_id", "")).strip()
            if preset_id and not any(item["id"] == preset_id for item in self._list_presets()):
                raise ValueError(f"unknown preset: {preset_id}")
            role_id = os.urandom(8).hex()
            role = self.registry.create_role(name, self.data_dir / "roles" / role_id, role_id=role_id)
            if preset_id:
                self._apply_role_preset(role.workspace, preset_id, name)
            self.registry.switch(role.role_id)
            self._bind_active()
            return self._bootstrap()
        if action == "preset_list":
            return self._list_presets()
        if action == "skills_list":
            return self.skills.snapshot()
        if action == "skill_enable":
            return self.skills.set_enabled(str(request["skill_id"]), request.get("enabled"))
        if action == "tool_invoke":
            return {"result": self.skills.invoke(str(request["name"]), dict(request.get("arguments") or {}))}
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
            package_value = request.get("package")
            if request.get("package_base64") is not None:
                encoded = str(request["package_base64"])
                if len(encoded) > 24_000_000:
                    raise ValueError("role package exceeds the 18 MB import limit")
                try:
                    package_bytes = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("role package payload is invalid base64") from exc
                if len(package_bytes) > 18_000_000:
                    raise ValueError("role package exceeds the 18 MB import limit")
                incoming = self.data_dir / "imports"
                incoming.mkdir(parents=True, exist_ok=True)
                package = incoming / f"{os.urandom(12).hex()}.cether-role"
                package.write_bytes(package_bytes)
            else:
                package = Path(str(package_value)).expanduser().resolve()
            workspace_value = request.get("workspace")
            workspace = (Path(str(workspace_value)).expanduser().resolve() if workspace_value else
                         self.data_dir / "roles" / f"imported-{os.urandom(8).hex()}")
            cfg = self.registry.import_package(package, workspace, conflict=str(request.get("conflict", "rename")),
                                               renamed_to=request.get("renamed_to"))
            if request.get("package_base64") is not None:
                package.unlink(missing_ok=True)
            return {"role_id": cfg.role_id, "name": cfg.name, "wake_pending": bool(self.registry.pending_wake(cfg.role_id))}
        if action == "set_mode":
            mode = request.get("mode")
            state = self._mode.set_override(mode)
            if mode is None:
                state = self._mode.state(self._foreground_app())
            return {"mode": state.mode, "source": state.source, "override": state.override}
        if action in {"active_expression", "expression_emit"}:
            text = str(request.get("text", "")).strip()
            if not text:
                raise ValueError("active expression text must not be empty")
            mode = self._expression_presentation()
            role_id = self.registry.active.config.role_id if self.registry.active else None
            if self._events:
                self._events.record("active_expression", text,
                                    metadata={"text": text, "presentation": mode, "role_id": role_id})
            return {"text": text, "presentation": mode, "role_id": role_id}
        if action == "set_expression_presentation":
            payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
            mode = str(request.get("mode", payload.get("mode", "")))
            if mode not in {"popup", "silent"}:
                raise ValueError("expression presentation must be popup or silent")
            path = self.data_dir / "expression-presentation.json"
            path.write_text(json.dumps({"mode": mode}, ensure_ascii=False), encoding="utf-8")
            return {"mode": mode}
        if action == "complete_onboarding":
            payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
            path = self.data_dir / "onboarding.json"
            path.write_text(json.dumps({"completed": True, "local_fallback": bool(request.get("local_fallback", payload.get("local_fallback", False)))}, ensure_ascii=False), encoding="utf-8")
            return self._bootstrap()
        if action == "tool_notice":
            return self._record_tool_result(request)
        if action == "send_message":
            if self.conversation is None:
                raise RuntimeError("no active conversation")
            turn = self.conversation.send(str(request.get("text", "")), mode=self._mode.state(self._foreground_app()).mode)
            observation = self.conversation.retrieval.last_observation
            retrieval = {
                "degraded": observation.error is not None,
                "channel": observation.channel,
                "error": observation.error,
                "result_count": observation.result_count,
                "budget_exceeded": observation.budget_exceeded,
            }
            return {"turn": asdict(turn), "history": self.conversation.history(), "retrieval": retrieval}
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
        if action == "runtime_events":
            if self._events is None:
                return {"events": [], "cursor": int(request.get("cursor", 0)), "paused": True,
                        "role_id": self.registry.active.config.role_id if self.registry.active else None}
            batch = self._events.subscribe(int(request.get("cursor", 0)), int(request.get("limit", 100)))
            batch["role_id"] = self.registry.active.config.role_id if self.registry.active else None
            return batch
        if action == "config_read":
            return self._read_config(str(request.get("name", "retrieval.toml")))
        if action == "config_write":
            return self._write_config(str(request.get("name", "retrieval.toml")), dict(request.get("values") or {}))
        if action == "memory_starfield":
            page = self.ui.memory_timeline(None, 500) if self.ui else None
            return self._starfield(list(page.records) if page else [])
        if action == "shutdown":
            self._stop_role_workers()
            self._snapshot_stop.set()
            if self._snapshot_thread and self._snapshot_thread is not threading.current_thread():
                self._snapshot_thread.join(timeout=5.0)
            self._snapshot_if_due(force=True)
            self.runtime = None
            self.conversation = None
            return {"stopped": True}
        raise ValueError(f"unknown action: {action}")

    def _bootstrap(self) -> dict[str, Any]:
        onboarding_path = self.data_dir / "onboarding.json"
        try:
            onboarding_state = json.loads(onboarding_path.read_text(encoding="utf-8")) if onboarding_path and onboarding_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            onboarding_state = {}
        presentation_path = self.data_dir / "expression-presentation.json"
        try:
            presentation = json.loads(presentation_path.read_text(encoding="utf-8")) if presentation_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            presentation = {}
        return {
            "expression_presentation": presentation.get("mode", "popup"),
            "onboarding": {"completed": bool(onboarding_state.get("completed")),
                           "local_fallback": bool(onboarding_state.get("local_fallback")),
                           "modules": ["对话与角色", "记忆分层", "感知授权", "窗口与休眠", "技能与工具", "配置与降级"]},
            "active_role": self._role_view(self.registry.active, active=True),
            "skills": self.skills.snapshot(),
            "roles": [self._role_view(_context(r), active=r.role_id == self.registry.active.config.role_id if self.registry.active else False)
                      for r in self.registry.list_roles()],
            "history": self.conversation.history() if self.conversation else [],
            "work_files": self._work_files(),
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
        self._stop_role_workers()
        self._lifecycle = MemoryLifecycleService(role, self.registry)
        self._diary = DiaryService(role, self.registry)
        self._seen_path = role.workspace / "world.jsonl"
        self._first_run_notice = FirstRunNotice(role.workspace / "sensing-consent.json")
        self._perception_config = load_perception_config(self.config_dir / "perception.toml")
        self._perceiver = self._build_perceiver(role)
        self._events = RuntimeEvents(role.workspace / "runtime-events.jsonl")
        cognition_path = self.config_dir / "cognition.toml"
        decision_config, expression_config = load_cognition_config(cognition_path)
        decision_provider = LocalDecisionProvider(decision_config)
        expression_provider = LocalExpressionProvider(expression_config)
        sleep_config_path = self.config_dir / "sleep.toml"
        sleep_service = SleepService(role, self.registry, config=load_sleep_config(sleep_config_path))
        sleep_schedule = SleepSchedule(load_sleep_schedule_config(sleep_config_path))
        spatial_provider = SpatialMemoryProvider(role, self.registry)
        graph_provider = LocalCooccurrenceGraphProvider(role, self.registry)
        embedding_path = self.config_dir / "embedding.toml"
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
            mode_provider=lambda: self._mode.state(self._foreground_app()).mode,
        )
        provider = LocalRuleProvider()
        onboarding_path = self.data_dir / "onboarding.json"
        try:
            onboarding_state = json.loads(onboarding_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            onboarding_state = {}
        config_path = Path(os.environ.get("CETHER_CHAT_CONFIG", self.data_dir / "chat.toml"))
        if not onboarding_state.get("local_fallback") and config_path.is_file():
            config = load_provider_config(config_path)
            if config.api_key():
                provider = OpenAICompatibleProvider(config)
        self.conversation = ConversationService(
            role=role, registry=self.registry, runtime=self.runtime, provider=provider,
            retrieval_config=RetrievalConfigWatcher(self.config_dir / "retrieval.toml"),
            injected_memories=self._consume_injections,
            injection_commit=self._lifecycle.commit_injections,
            context_budget=load_budget_config(self.config_dir / "context_budget.toml"),
            budget_event_sink=lambda payload: self._events.record("context_budget", "单轮上下文预算裁决", metadata=payload)
                if self._events else None,
            excluded_ids=lambda: self._lifecycle.excluded_ids() if self._lifecycle else frozenset(),
        )
        self.ui = self._build_ui_contract(role)
        self._start_role_workers()

    def _start_role_workers(self) -> None:
        if self.runtime is None or self.registry.active is None:
            return
        self._pipeline_stop = threading.Event()
        self._scheduler_stop = threading.Event()
        self._next_checkpoint_at = time.monotonic()
        self.runtime.build_pipeline(event_sink=self._pipeline_event)
        self._pipeline_thread = threading.Thread(target=self._run_pipeline, name="cether-runtime", daemon=True)
        self._pipeline_thread.start()
        self._scheduler_thread = threading.Thread(target=self._run_scheduler, name="cether-checkpoint", daemon=True)
        self._scheduler_thread.start()

    def _stop_role_workers(self) -> None:
        self._pipeline_stop.set()
        self._scheduler_stop.set()
        if self.runtime:
            self.runtime.cancel()
        for thread in (self._pipeline_thread, self._scheduler_thread):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=30.0)
        self._pipeline_thread = None
        self._scheduler_thread = None
        if self.runtime:
            self.runtime.close()
        self._snapshot_if_due(force=True)

    def _run_pipeline(self) -> None:
        runtime = self.runtime
        if runtime is None or runtime._pipeline is None:
            return
        try:
            runtime._pipeline.run(should_stop=self._pipeline_stop.is_set)
        except Exception as exc:
            if self._events:
                self._events.record("runtime_error", str(exc))

    def _pipeline_event(self, event: Any) -> None:
        if self._events:
            self._events.record(f"pipeline_{event.stage}_{event.status}", event.detail,
                                metadata={"tick_id": event.tick_id, "role_scope": event.role_scope})
        if event.stage == "result_feedback" and event.status == "completed":
            self._snapshot_turns += 1
            self._snapshot_if_due()

    def _snapshot_if_due(self, *, force: bool = False) -> None:
        if not self._snapshot_lock.acquire(blocking=False):
            return
        try:
            self._snapshot_if_due_locked(force=force)
        finally:
            self._snapshot_lock.release()

    def _snapshot_if_due_locked(self, *, force: bool = False) -> None:
        role = self.registry.active
        if role is None:
            return
        config_path = role.workspace / "checkpoint.toml"
        rounds = 10
        interval = 300.0
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
            checkpoint = raw.get("persistence", {})
            rounds = max(1, int(checkpoint.get("snapshot_every_turns", rounds)))
            interval = max(10.0, float(checkpoint.get("snapshot_every_seconds", interval)))
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            if self._events:
                self._events.record("snapshot_config_error", str(exc))
        now = time.monotonic()
        if force or self._snapshot_turns >= rounds or now - getattr(self, "_last_snapshot_at", 0.0) >= interval:
            try:
                self.registry._commit_workspace_snapshot(role)
                self._snapshot_turns = 0
                self._last_snapshot_at = now
            except Exception as exc:
                if self._events:
                    self._events.record("snapshot_error", str(exc))

    def _start_snapshot_worker(self) -> None:
        self._snapshot_stop = threading.Event()
        def run() -> None:
            while not self._snapshot_stop.wait(30.0):
                self._snapshot_if_due()
        self._snapshot_thread = threading.Thread(target=run, name="cether-snapshot", daemon=True)
        self._snapshot_thread.start()

    def _run_scheduler(self) -> None:
        role = self.registry.active
        if role is None:
            return
        config_path = role.workspace / "window.toml"
        if not config_path.is_file():
            config_path = self.config_dir / "window.toml"
        if not config_path.is_file():
            config_path = Path(__file__).resolve().parents[2] / "config" / "window.toml"
        try:
            config, windows = load_window_config(config_path)
        except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as exc:
            if self._events:
                self._events.record("scheduler_config_error", str(exc))
            return
        expression_config_path = self.config_dir / "active_expression.toml"
        if not expression_config_path.is_file():
            expression_config_path = Path(__file__).resolve().parents[2] / "config" / "active_expression.toml"
        try:
            expression_cfg = tomllib.loads(expression_config_path.read_text(encoding="utf-8")).get("expression", {})
        except (OSError, tomllib.TOMLDecodeError):
            expression_cfg = {}
        interval_mode = "fixed"
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            interval_mode = str(raw.get("checkpoint", {}).get("interval_mode", "fixed"))
        except (OSError, tomllib.TOMLDecodeError):
            pass
        self._next_checkpoint_at = time.monotonic() + self._next_interval(config, interval_mode)
        while not self._scheduler_stop.wait(1.0):
            now = datetime.now().astimezone()
            mode = self._mode.state(self._foreground_app())
            sleep_mode = self.runtime._sleep_mode if self.runtime else "awake"
            state = self.runtime._read_state() if self.runtime else {}
            reason = checkpoint_block_reason(
                now, windows, sleep_mode in {"light", "deep"}, mode.mode == "silent",
                self._hourly_fires, config.hourly_cap,
                momentary_valence=float(state.get("momentary_valence", 0.0)),
                relation_tension=float(state.get("relation_tension", 0.0)),
            )
            pending_text = str(state.get("pending_expression", "")).strip()
            if not pending_text and expression_cfg.get("enabled", True):
                pending_text = self._active_expression_candidate(role, now, expression_cfg)
            if mode.mode not in expression_cfg.get("allowed_modes", ["companion"]):
                pending_text = ""
                reason = reason or "mode_blocked"
            if pending_text and self._is_rejected_expression(pending_text, expression_cfg):
                self._rejected_expression_keys.add(self._expression_key(pending_text))
                pending_text = ""
                reason = reason or "candidate_rejected"
            if pending_text and self._last_active_expression_at:
                cooldown = int(expression_cfg.get("cooldown_seconds", 1800))
                if (now - self._last_active_expression_at).total_seconds() < cooldown:
                    pending_text = ""
                    reason = reason or "cooldown"
            daily_cap = int(expression_cfg.get("daily_cap", 3))
            today_fires = [stamp for stamp in self._hourly_fires if stamp.date() == now.date()]
            if pending_text and len(today_fires) >= daily_cap:
                pending_text = ""
                reason = reason or "daily_cap_reached"
            if not reason and not pending_text:
                reason = "no_grounded_candidate"
            if reason:
                if self._events and reason != getattr(self, "_last_scheduler_reason", None):
                    self._events.record("checkpoint_blocked", reason)
                self._last_scheduler_reason = reason
                continue
            if time.monotonic() < self._next_checkpoint_at:
                continue
            self._last_scheduler_reason = None
            impulse = float(state.get("expression_impulse", state.get("expression_impulse_projection", 0.0)))
            mind_box = self._load_mind_box(role.workspace)
            result = run_checkpoint(now=now, expression_impulse=impulse,
                                    impulse_threshold=config.impulse_threshold, gate_reason=None,
                                    hesitation_resolution=Outcome.SPOKE if pending_text else Outcome.WITHDRAWN,
                                    mind_box=mind_box, hesitation_text=pending_text)
            self._save_mind_box(role.workspace, mind_box)
            if result.outcome == Outcome.SPOKE:
                self._hourly_fires.append(now)
                self._missed_checkpoints = 0
                text = result.hesitation_text or ""
                if text:
                    presentation = self._expression_presentation()
                    if self.conversation:
                        self.conversation.record_proactive(text, persist=presentation != "silent")
                    self._emit_active_expression(text)
                    self._last_active_expression_at = now
                    self._mark_expression_used(role.workspace, text, now)
            else:
                self._missed_checkpoints += 1
                if self._events:
                    self._events.record("checkpoint_mind_box", result.reason or result.outcome.value)
            self._hourly_fires = [stamp for stamp in self._hourly_fires if now - stamp < timedelta(hours=1)]
            self._next_checkpoint_at = time.monotonic() + self._next_interval(config, interval_mode)

    @staticmethod
    def _expression_key(text: str) -> str:
        return " ".join(text.casefold().split())

    def _is_rejected_expression(self, text: str, config: dict[str, Any]) -> bool:
        key = self._expression_key(text)
        if key in self._rejected_expression_keys:
            return True
        state = self.runtime._read_state() if self.runtime else {}
        if state.get("expression_rejected"):
            return True
        tags = [str(tag).casefold() for tag in config.get("rejection_tags", [])]
        return any(tag in text.casefold() for tag in tags)

    def _active_expression_candidate(self, role: RoleContext, now: datetime, config: dict[str, Any]) -> str:
        """Choose existing role-local notes; never synthesize prose from nothing."""
        try:
            used_path = role.workspace / "active-expression-state.json"
            used = json.loads(used_path.read_text(encoding="utf-8")) if used_path.is_file() else {}
            used_keys = set(used.get("used", []))
            candidates: list[tuple[float, str]] = []
            for item in self._load_mind_box(role.workspace).items:
                text = str(item.get("text", "")).strip()
                if text and item.get("kind") in {"hesitation", "reflection"}:
                    candidates.append((3.0, text))
            if self._diary:
                for item in self._diary.list_entries()[:20]:
                    text = str(item.get("narrative", "")).strip()
                    if text:
                        candidates.append((2.0, text))
            l0_path = role.workspace / "memory" / "l0.jsonl"
            if l0_path.is_file():
                cutoff = now.timestamp() - int(config.get("lookback_days", 14)) * 86400
                for item in L0Archive(l0_path):
                    metadata = item.get("tier_metadata", {})
                    if metadata.get("memory_tier") != "high" and not metadata.get("manual_mark") and not metadata.get("flash_weight"):
                        continue
                    text = str(item.get("text", "")).strip()
                    try:
                        stamp = datetime.fromisoformat(str(item.get("ts"))).timestamp()
                    except (ValueError, TypeError, OSError):
                        continue
                    if text and stamp >= cutoff:
                        candidates.append((1.0, text))
            rejected = [str(tag).casefold() for tag in config.get("rejection_tags", [])]
            for _, text in sorted(candidates, key=lambda item: item[0], reverse=True):
                key = self._expression_key(text)
                if key in used_keys or key in self._rejected_expression_keys:
                    continue
                if any(tag in text.casefold() for tag in rejected):
                    continue
                return text
        except (OSError, ValueError, TypeError, KeyError):
            return ""
        return ""

    @staticmethod
    def _mark_expression_used(workspace: Path, text: str, now: datetime) -> None:
        path = workspace / "active-expression-state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, ValueError, TypeError):
            data = {}
        used = list(data.get("used", []))
        used.append(DesktopRuntime._expression_key(text))
        payload = {"used": used[-200:], "last_sent_at": now.isoformat()}
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def _next_interval(self, config: Any, mode: str) -> float:
        if mode == "random":
            return next_random_interval(config, self._scheduler_rng, self._missed_checkpoints)
        return next_fixed_interval(config, self._scheduler_rng, self._missed_checkpoints)

    @staticmethod
    def _load_mind_box(workspace: Path) -> MindBox:
        path = workspace / "mind_box.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
            return MindBox(items=list(raw) if isinstance(raw, list) else [])
        except (OSError, ValueError, TypeError):
            return MindBox()

    @staticmethod
    def _save_mind_box(workspace: Path, result: Any) -> None:
        path = workspace / "mind_box.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(result.items, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _emit_active_expression(self, text: str) -> None:
        mode = self._expression_presentation()
        if self._events:
            self._events.record("active_expression", text,
                                metadata={"text": text, "presentation": mode,
                                          "role_id": self.registry.active.config.role_id if self.registry.active else None})

    def _expression_presentation(self) -> str:
        try:
            raw = json.loads((self.data_dir / "expression-presentation.json").read_text(encoding="utf-8"))
            return "silent" if raw.get("mode") == "silent" else "popup"
        except (OSError, ValueError, TypeError):
            return "popup"

    def _build_ui_contract(self, role: RoleContext) -> UiContract:
        return UiContract(
            role_cards=self._role_cards,
            status=self._status_view,
            look_now=self._look_now,
            set_capture_paused=self._set_capture_paused,
            set_events_paused=self._set_events_paused,
            remember_this=self._remember_this,
            think_again=self._think_again,
            deepen=self._deepen_memory,
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
            vision_path = self.config_dir / "vision.toml"
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

    def _work_files(self) -> list[dict[str, str]]:
        role = self.registry.active
        if role is None:
            return []
        root = role.workspace / "work-files"
        if not root.is_dir():
            return []
        results: list[dict[str, str]] = []
        for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
            if not path.is_file():
                continue
            try:
                results.append({"name": path.name, "path": path.relative_to(role.workspace).as_posix(),
                                "content": path.read_text(encoding="utf-8")})
            except (OSError, UnicodeError):
                continue
        return results

    def _record_tool_result(self, request: dict[str, Any]) -> dict[str, Any]:
        """Record active-role tool context and optionally persist its artifact, never to memory by default."""
        role = self.registry.active
        if role is None:
            raise RuntimeError("tool result requires an active role")
        kind = str(request.get("kind", "tool"))
        description = str(request.get("description", ""))
        status = str(request.get("status", "success"))
        if status not in {"success", "failure", "timeout"}:
            raise ValueError("tool result status must be success, failure, or timeout")
        artifact_name = request.get("artifact_name")
        artifact_path = None
        work_path = None
        if artifact_name is not None:
            name = Path(str(artifact_name)).name
            if not name or name in {".", ".."} or name != str(artifact_name):
                raise ValueError("artifact_name must be a plain filename")
            artifact_dir = role.workspace / "artifacts" / "tools"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_dir / name
            payload = request.get("artifact_content", "")
            if not isinstance(payload, str):
                raise ValueError("artifact_content must be text")
            artifact_path.write_text(payload, encoding="utf-8")
            if status == "success" and self._mode.state(self._foreground_app()).mode == "work":
                work_dir = role.workspace / "work-files"
                work_dir.mkdir(parents=True, exist_ok=True)
                work_path = work_dir / name
                work_path.write_text(payload, encoding="utf-8")
        event_data = {"role_id": role.config.role_id, "status": status,
                      "artifact": artifact_path.relative_to(role.workspace).as_posix() if artifact_path else None,
                      "work_file": work_path.relative_to(role.workspace).as_posix() if work_path else None,
                      "memory_written": False}
        event_kind = f"tool_{status}" if status != "success" else kind
        if self._events:
            self._events.record(event_kind, description, metadata=event_data)
        if status in {"failure", "timeout"}:
            RuntimeEvents(role.workspace / "world.jsonl").record(event_kind, description, metadata=event_data)
        return {"visible": True, "status": status, **event_data}

    def _think_again(self, memory_id: str) -> bool:
        if not self._lifecycle:
            raise RuntimeError("memory lifecycle unavailable")
        record = self._lifecycle._record(memory_id)
        self._events.record("memory_reflection_requested", str(record.get("text", ""))[:240]) if self._events else None
        return True

    def _deepen_memory(self, memory_id: str) -> float:
        if not self._lifecycle:
            raise RuntimeError("memory lifecycle unavailable")
        weight = self._lifecycle.deepen(memory_id)
        self._events.record("memory_deepened", memory_id) if self._events else None
        return weight

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

    def _list_presets(self) -> list[dict[str, Any]]:
        presets_dir = self.data_dir / "presets"
        results: list[dict[str, Any]] = []
        for path in sorted(presets_dir.glob("*.yaml")):
            rows = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                if ":" in line and not line.startswith(" "):
                    key, value = line.split(":", 1)
                    rows[key.strip()] = value.strip()
            results.append({"id": rows.get("id", path.stem), "version": rows.get("version", "1"),
                            "name": rows.get("name", path.stem), "file": path.name})
        return results

    def _apply_role_preset(self, workspace: Path, preset_id: str, name: str) -> None:
        preset = next((item for item in self._list_presets() if item["id"] == preset_id), None)
        if preset is None:
            raise ValueError(f"unknown preset: {preset_id}")
        payload = (self.data_dir / "presets" / preset["file"]).read_text(encoding="utf-8")
        persona = next((line[2:] for line in payload.splitlines() if line.startswith("  style:")), "").strip()
        boundaries = next((line[2:] for line in payload.splitlines() if line.startswith("  boundaries:")), "").strip()
        (workspace / "persona.md").write_text(f"# {name}\n\n{persona}\n", encoding="utf-8")
        (workspace / "boundaries.md").write_text(f"# 边界\n\n{boundaries}\n", encoding="utf-8")
        mode = next((line.split(":", 1)[1].strip() for line in payload.splitlines() if line.strip().startswith("mode:")), "companion")
        (workspace / "role-preset.json").write_text(json.dumps({"id": preset_id, "version": preset["version"],
            "mode": mode}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_config(self, name: str) -> dict[str, Any]:
        path = self._config_path(name)
        if not path.exists():
            return {"name": name, "values": {}, "exists": False}
        with path.open("rb") as stream:
            values = tomllib.load(stream)
        return {"name": name, "values": values, "exists": True}

    def _write_config(self, name: str, values: dict[str, Any]) -> dict[str, Any]:
        path = self._config_path(name)
        if name not in {"retrieval.toml", "cognition.toml", "perception.toml", "sleep.toml", "embedding.toml", "vision.toml", "context_budget.toml", "window.toml"}:
            raise ValueError("this configuration format is not editable through the panel")
        if not isinstance(values, dict) or not values or any(not isinstance(section, dict) for section in values.values()):
            raise ValueError("configuration must contain one or more TOML tables")
        current = self._read_config(name).get("values", {})
        if set(values) != set(current):
            raise ValueError("configuration tables must match the existing file")
        for table, section in values.items():
            existing = current.get(table, {})
            if set(section) != set(existing):
                raise ValueError(f"configuration keys must match the existing [{table}] table")
            for key, value in section.items():
                expected_type = type(existing[key])
                compatible = type(value) is expected_type or (expected_type is float and type(value) is int)
                if not compatible:
                    raise ValueError(f"configuration value type mismatch for [{table}].{key}")
        if name == "retrieval.toml":
            section = values.get("retrieval", {})
            if not 1 <= int(section.get("top_k", 8)) <= 500 or float(section.get("latency_budget_ms", 300)) <= 0:
                raise ValueError("top_k and latency_budget_ms are out of range")
        def toml_value(value: Any) -> str:
            if isinstance(value, bool): return "true" if value else "false"
            if isinstance(value, (int, float)): return repr(value)
            if isinstance(value, str): return json.dumps(value, ensure_ascii=False)
            if isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
                return "[" + ", ".join(toml_value(item) for item in value) + "]"
            if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, (str, int, float, bool)) for k, v in value.items()):
                return "{ " + ", ".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in sorted(value.items())) + " }"
            raise ValueError("unsupported TOML value")
        blocks: list[str] = []
        for table, section_values in values.items():
            lines = [f"[{table}]"]
            lines.extend(f"{key} = {toml_value(value)}" for key, value in sorted(section_values.items()))
            blocks.append("\n".join(lines))
        content = "\n\n".join(blocks) + "\n"
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
        return self._read_config(name)

    def _config_path(self, name: str) -> Path:
        if Path(name).name != name or not name.endswith(".toml"):
            raise ValueError("configuration name must be a TOML filename")
        return self.config_dir / name

    def _starfield(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        index_path = self.registry.active.workspace / "memory" / "spatial-index.json"
        index = SpatialIndex.load(index_path)
        nodes: list[dict[str, Any]] = []
        token_sets: dict[str, set[str]] = {}
        for record in records:
            memory_id = str(record.get("id", ""))
            if not memory_id:
                continue
            tier = record.get("tier_metadata") or {}
            metadata = record.get("metadata") or {}
            index.assign(memory_id)
            coords = index.slot_of(memory_id)
            if coords is None:
                continue
            lifecycle = str(record.get("lifecycle_status", "hot"))
            weight = float(tier.get("weight", 1.0 if tier.get("memory_tier") == "high" else 0.5))
            if lifecycle == "cooling":
                weight *= float(record.get("lifecycle_weight_factor", 0.5))
            elif lifecycle in {"cold", "deleted"}:
                weight = 0.0
            nodes.append({"memory_id": memory_id, "text": record.get("text", ""), "room": coords.room,
                          "slot_id": coords.slot, "room_capacity": index.config.room_capacity,
                          "weight": max(0.0, min(1.0, weight)),
                          "category": "relation" if metadata.get("is_relation_event") else "emotion" if metadata.get("emotion_intensity", 0) else "fact",
                          "timestamp": record.get("ts", ""), "archived": lifecycle in {"cold", "deleted"},
                          "lifecycle_status": lifecycle})
            token_sets[memory_id] = set(tokenize(str(record.get("text", ""))))
        index.save(index_path)
        edge_rows: list[dict[str, Any]] = []
        ids = sorted(token_sets)
        for offset, source_id in enumerate(ids):
            for target_id in ids[offset + 1:]:
                left, right = token_sets[source_id], token_sets[target_id]
                overlap = len(left & right)
                if overlap:
                    edge_rows.append({"source": source_id, "target": target_id,
                                      "weight": overlap / max(1, len(left | right))})
        projected = memory_starfield(nodes)
        return {"nodes": [{**asdict(node), "x": node.x / 1000, "y": node.y / 700,
                            "lifecycle_status": nodes[i]["lifecycle_status"]}
                           for i, node in enumerate(projected)],
                "edges": edge_rows, "total": len(projected), "view": "galaxy"}

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
        memory_id = self.runtime._l0.append(text.strip(), "manual", metadata={"manual_mark": True, "memory_tier": "high"})
        if self._events:
            self._events.record("memory_created", memory_id)
        return memory_id

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
    # Force UTF-8 encoding for stdout to avoid "stream did not contain valid UTF-8" errors on Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    
    data_dir = Path(sys.argv[1]).expanduser().resolve()
    runtime = DesktopRuntime(data_dir)
    try:
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
    finally:
        runtime.handle({"action": "shutdown"})


if __name__ == "__main__":
    main()
