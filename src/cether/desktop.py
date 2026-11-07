"""JSON-lines bridge used by the Tauri desktop shell."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from .conversation import ConversationService
from .providers import LocalRuleProvider, OpenAICompatibleProvider, load_provider_config
from .roles import RoleRegistry
from .runtime_services import RuntimeServices
from .trigger import TriggerConfig


class DesktopRuntime:
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
        self._bind_active()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "bootstrap":
            active_id = self.registry.active.config.role_id if self.registry.active else None
            return {"active_role": self._role_view(self.registry.active, active=True),
                    "roles": [self._role_view(_context(r), active=r.role_id == active_id) for r in self.registry.list_roles()],
                    "history": self.conversation.history() if self.conversation else []}
        if action == "create_role":
            name = str(request.get("name", "")).strip()
            if not name:
                raise ValueError("role name must not be empty")
            role_id = os.urandom(8).hex()
            role = self.registry.create_role(name, self.data_dir / "roles" / role_id, role_id=role_id)
            self.registry.switch(role.role_id)
            self._bind_active()
            return self.handle({"action": "bootstrap"})
        if action == "switch_role":
            result = self.registry.switch(str(request["role_id"]))
            if result.error:
                raise RuntimeError(result.error)
            self._bind_active()
            return self.handle({"action": "bootstrap"})
        if action == "send_message":
            if self.conversation is None:
                raise RuntimeError("no active conversation")
            turn = self.conversation.send(str(request.get("text", "")))
            return {"turn": turn.__dict__, "history": self.conversation.history()}
        if action == "shutdown":
            if self.runtime:
                self.runtime.close()
                self.runtime = None
                self.conversation = None
            return {"stopped": True}
        raise ValueError(f"unknown action: {action}")

    def _bind_active(self) -> None:
        role = self.registry.active
        if role is None:
            self.runtime = None
            self.conversation = None
            return
        if self.runtime:
            self.runtime.close()
        self.runtime = RuntimeServices(
            role=role, registry=self.registry, trigger_config=TriggerConfig(0.7, 0.7, 3600),
            perceive=lambda: None, decision=lambda _request: None,
            expression=lambda _decision, _request: None,
        )
        provider = LocalRuleProvider()
        config_path = Path(os.environ.get("CETHER_CHAT_CONFIG", self.data_dir / "chat.toml"))
        if config_path.is_file():
            config = load_provider_config(config_path)
            if config.api_key():
                provider = OpenAICompatibleProvider(config)
        self.conversation = ConversationService(role=role, registry=self.registry, runtime=self.runtime, provider=provider)

    @staticmethod
    def _role_view(context, *, active: bool = False) -> dict[str, Any] | None:
        if context is None:
            return None
        return {"role_id": context.config.role_id, "name": context.config.name,
                "active": active, "self_awareness": context.config.self_awareness}


def _context(config):
    from .roles import RoleContext
    return RoleContext(config, config.role_id)


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
