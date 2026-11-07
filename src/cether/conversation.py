"""Explicit, role-scoped conversation service independent of background sensing."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .l0 import L0Archive
from .providers import ConversationProvider, LocalRuleProvider, TurnRequest
from .roles import RoleContext, RoleRegistry
from .runtime_services import RuntimeServices
from .state import StateSnapshot


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    timestamp: str
    kind: str
    emotion: str


class ConversationService:
    """Persist and generate explicit user turns for exactly one active role."""

    def __init__(
        self,
        *,
        role: RoleContext,
        registry: RoleRegistry,
        runtime: RuntimeServices,
        provider: ConversationProvider | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.role = role
        self.registry = registry
        self.runtime = runtime
        self.provider = provider or LocalRuleProvider()
        self.clock = clock
        self._lock = threading.Lock()
        self._history_path = role.workspace / "conversation.jsonl"
        self._l0 = L0Archive(role.workspace / "memory" / "l0.jsonl")

    def send(self, text: str) -> ConversationTurn:
        """Generate one response, persist both sides, and feed expression state."""
        user_text = text.strip()
        if not user_text:
            raise ValueError("message must not be empty")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("a conversation turn is already in progress")
        try:
            self.registry.ensure_role_scope(self.role.scope_id)
            state = self.runtime._read_state()
            wake = self.runtime.pending_wake_context()
            memories = tuple(record["text"] for record in list(self._l0)[-8:])
            request = TurnRequest(
                role_name=self.role.config.name,
                persona=self._persona(),
                user_text=user_text,
                state=state,
                recent_memories=memories,
                wake_context=wake,
            )
            response = self.provider.respond(request)
            if not response.text.strip():
                raise ValueError("provider returned an empty response")
            self.registry.ensure_role_scope(self.role.scope_id)
            consumed_wake = self.runtime.begin_user_turn()
            if consumed_wake != wake:
                raise RuntimeError("wake context changed during the conversation turn")
            now = self.clock().isoformat()
            user_turn = ConversationTurn("user", user_text, now, "user", "neutral")
            assistant_turn = ConversationTurn("assistant", response.text.strip(), now, response.kind, response.emotion)
            self._append(user_turn)
            self._append(assistant_turn)
            self._l0.append(user_text, "conversation")
            self._l0.append(response.text.strip(), "conversation")
            feedback = self.runtime._feed_result(None, asdict(response), StateSnapshot(self.clock().timestamp(), state))
            return ConversationTurn(assistant_turn.role, assistant_turn.text, assistant_turn.timestamp,
                                   assistant_turn.kind, assistant_turn.emotion)
        finally:
            self._lock.release()

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

    def _persona(self) -> str:
        path = self.role.workspace / "persona.md"
        return path.read_text(encoding="utf-8") if path.is_file() else ""
