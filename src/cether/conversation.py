"""Explicit, role-scoped conversation service independent of background sensing."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .l0 import L0Archive
from .memory_retrieval import L0RetrievalService, RetrievalConfigWatcher
from .providers import ConversationProvider, LocalRuleProvider, TurnRequest
from .cognition import resolve_expression
from .roles import RoleContext, RoleRegistry
from .runtime_services import RuntimeServices
from .retrieval import RetrievalResult
from .state import StateSnapshot
from .backchannel import BackchannelHandle, BackchannelScheduler
from .context_budget import BudgetConfig, ContextSegment, allocate_budget


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    timestamp: str
    kind: str
    emotion: str
    directive: dict[str, str | None] | None = None
    resolved_expression: dict[str, str | bool | None] | None = None


class ConversationService:
    """Persist and generate explicit user turns for exactly one active role."""

    def __init__(
        self,
        *,
        role: RoleContext,
        registry: RoleRegistry,
        runtime: RuntimeServices,
        provider: ConversationProvider | None = None,
        retrieval: L0RetrievalService | None = None,
        retrieval_config: RetrievalConfigWatcher | None = None,
        injected_memories: Callable[[], tuple[dict, ...]] | None = None,
        excluded_ids: Callable[[], frozenset[str]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        backchannel: BackchannelScheduler | None = None,
        context_budget: BudgetConfig | None = None,
        budget_event_sink: Callable[[dict], None] | None = None,
        injection_commit: Callable[[tuple[dict, ...]], None] | None = None,
    ) -> None:
        self.role = role
        self.registry = registry
        self.runtime = runtime
        self.provider = provider or LocalRuleProvider()
        self.clock = clock
        self.backchannel = backchannel
        self.context_budget = context_budget or BudgetConfig()
        self.budget_event_sink = budget_event_sink
        self.injection_commit = injection_commit
        self.injected_memories = injected_memories
        self.excluded_ids = excluded_ids
        self._lock = threading.Lock()
        self._history_path = role.workspace / "conversation.jsonl"
        self._l0 = L0Archive(role.workspace / "memory" / "l0.jsonl")
        self.retrieval = retrieval or L0RetrievalService(
            role, registry, self._l0,
            retrieval_config or RetrievalConfigWatcher(Path(__file__).resolve().parents[2] / "config" / "retrieval.toml"),
            spatial_provider=getattr(runtime, "spatial_provider", None),
            embedding_provider=getattr(runtime, "embedding_provider", None),
            graph_provider=getattr(runtime, "graph_provider", None),
            excluded_ids=excluded_ids,
        )

    def send(self, text: str, *, mode: str = "companion") -> ConversationTurn:
        """Generate one response, persist both sides, and feed expression state."""
        return self._respond(text, persist_user=True, kind="conversation", mode=mode)

    def record_proactive(self, text: str, *, persist: bool) -> ConversationTurn:
        """Record a scheduled utterance without inventing a user message or model call."""
        value = text.strip()
        if not value:
            raise ValueError("proactive expression must not be empty")
        self.registry.ensure_role_scope(self.role.scope_id)
        with self._lock:
            now = self.clock().isoformat()
            turn = ConversationTurn("assistant", value, now, "proactive_expression", "neutral")
            if persist:
                self._append(turn)
                self._l0.append(value, "proactive_expression")
            return turn

    def _respond(self, text: str, *, persist_user: bool, kind: str, persist: bool = True) -> ConversationTurn:
        user_text = text.strip()
        if not user_text:
            raise ValueError("message must not be empty")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("a conversation turn is already in progress")
        backchannel_handle: BackchannelHandle | None = None
        try:
            self.registry.ensure_role_scope(self.role.scope_id)
            if self.backchannel is not None:
                backchannel_handle = self.backchannel.start(user_text)
            state = self.runtime._read_state()
            wake = self.runtime.pending_wake_context()
            memories = self.retrieval.search(user_text)
            injected = self._pending_injections = (self.injected_memories() if self.injected_memories is not None else ())
            candidates = [ContextSegment("persona_anchor", self._persona())]
            boundary_path = self.role.workspace / "boundaries.md"
            if boundary_path.is_file():
                boundary = boundary_path.read_text(encoding="utf-8").strip()
                if boundary:
                    candidates.append(ContextSegment("hard_boundary", boundary))
            state_text = json.dumps(state, ensure_ascii=False, sort_keys=True)
            candidates.append(ContextSegment("state_texture", state_text, self.clock().timestamp()))
            for item in injected:
                if item.get("text"):
                    candidates.append(ContextSegment("mind_box", str(item["text"]), self._timestamp(item)))
            for index, memory in enumerate(memories):
                candidates.append(ContextSegment("recall_memory", str(memory), float(len(memories) - index)))
            continuation = self._continuation_summary()
            if continuation:
                candidates.append(ContextSegment("session_continuation", continuation, self.clock().timestamp()))
            budget = allocate_budget(candidates, self.context_budget)
            if self.budget_event_sink:
                self.budget_event_sink({"decisions": [asdict(decision) for decision in budget.decisions]})
            kept = {segment.category: [] for segment in budget.segments}
            for segment in budget.segments:
                kept.setdefault(segment.category, []).append(segment.text)
            persona = "\n\n".join(kept.get("persona_anchor", []))
            if kept.get("hard_boundary"):
                persona += "\n\n硬边界：\n" + "\n".join(kept["hard_boundary"])
            if kept.get("state_texture"):
                persona += "\n\n当前状态：" + "\n".join(kept["state_texture"])
            memories = tuple(kept.get("mind_box", []) + kept.get("recall_memory", []))
            wake_parts = [wake] if wake else []
            wake_parts.extend(kept.get("session_continuation", []))
            request = TurnRequest(
                role_name=self.role.config.name,
                persona=persona,
                user_text=user_text,
                state=state,
                recent_memories=memories,
                wake_context="\n\n".join(wake_parts) or None,
                self_awareness=self.role.config.self_awareness,
            )
            if backchannel_handle is not None:
                backchannel_handle.cancel()
            response = self.provider.respond(request)
            if not response.text.strip():
                raise ValueError("provider returned an empty response")
            directive = asdict(response.directive) if response.directive is not None else None
            resolved = resolve_expression({"text": response.text.strip(), "kind": response.kind,
                                          "emotion": response.emotion, "directive": directive})
            resolved_data = asdict(resolved)
            self.registry.ensure_role_scope(self.role.scope_id)
            consumed_wake = self.runtime.begin_user_turn()
            if consumed_wake != wake:
                raise RuntimeError("wake context changed during the conversation turn")
            now = self.clock().isoformat()
            user_turn = ConversationTurn("user", user_text, now, "user", "neutral")
            assistant_turn = ConversationTurn("assistant", response.text.strip(), now, response.kind, response.emotion, directive, resolved_data)
            self._append(user_turn)
            self._append(assistant_turn)
            self._l0.append(user_text, "conversation")
            self._l0.append(response.text.strip(), "conversation")
            feedback = self.runtime._feed_result(None, asdict(response), StateSnapshot(self.clock().timestamp(), state))
            self._commit_injections()
            self._write_continuation_summary()
            return ConversationTurn(assistant_turn.role, assistant_turn.text, assistant_turn.timestamp,
                                   assistant_turn.kind, assistant_turn.emotion, assistant_turn.directive, assistant_turn.resolved_expression)
        finally:
            if backchannel_handle is not None:
                backchannel_handle.cancel()
            self._lock.release()

    def _commit_injections(self) -> None:
        if getattr(self, "_pending_injections", None) and self.injection_commit is not None:
            self.injection_commit(self._pending_injections)
        self._pending_injections = ()

    def _continuation_summary(self) -> str | None:
        mode = self.runtime.get_current_mode() if hasattr(self.runtime, "get_current_mode") else "companion"
        if mode == "work":
            path = self.role.workspace / "work-session-continuation.json"
        else:
            path = self.role.workspace / "session-continuation.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            turns = self.history(limit=500)
            if len(turns) > int(data.get("max_turns", 80)):
                return None
            return str(data.get("summary", "")).strip() or None
        except (OSError, ValueError, TypeError):
            return None

    def _write_continuation_summary(self) -> None:
        turns = self.history(limit=500)
        if not turns:
            return
        max_turns = 80
        summary_limit = 200
        summary = "；".join(f"{row.get('role')}: {str(row.get('text', ''))[:70]}" for row in turns[-4:])
        payload = {"summary": summary[:summary_limit], "max_turns": max_turns,
                   "updated_at": self.clock().isoformat()}
        mode = self.runtime.get_current_mode() if hasattr(self.runtime, "get_current_mode") else "companion"
        if mode == "work":
            path = self.role.workspace / "work-session-continuation.json"
        else:
            path = self.role.workspace / "session-continuation.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def history(self, limit: int = 100) -> list[dict[str, str]]:
        """Read this role's latest conversation turns."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        self.registry.ensure_role_scope(self.role.scope_id)
        if not self._history_path.exists():
            return []
        lines = self._history_path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]

    def _append(self, turn: ConversationTurn) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(asdict(turn), ensure_ascii=False) + "\n")
            stream.flush()

    @staticmethod
    def _timestamp(item: dict) -> float:
        value = item.get("ts", item.get("timestamp", 0.0))
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError, OSError):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

    def _persona(self) -> str:
        """Load role-owned persona and self-awareness text for this turn only."""
        sections: list[str] = [
            f"角色自我认知档位（由用户角色卡设定）：{self.role.config.self_awareness}"
        ]
        persona_path = self.role.workspace / "persona.md"
        if persona_path.is_file():
            sections.append(persona_path.read_text(encoding="utf-8").strip())
        awareness_path = self.role.workspace / "self_awareness.md"
        if awareness_path.is_file():
            awareness = awareness_path.read_text(encoding="utf-8").strip()
            if awareness:
                sections.append("角色自我认知设定（仅遵循本角色文本）：\n" + awareness)
        boundaries_path = self.role.workspace / "boundaries.md"
        if boundaries_path.is_file():
            boundaries = boundaries_path.read_text(encoding="utf-8").strip()
            if boundaries:
                sections.append("本角色硬边界：\n" + boundaries)
        return "\n\n".join(section for section in sections if section)
