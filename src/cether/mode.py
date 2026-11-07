"""Companion/work mode selection with explicit manual override."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeState:
    mode: str = "companion"
    source: str = "automatic"
    override: str | None = None


class ModeController:
    """Classify foreground applications while allowing a visible manual override."""

    def __init__(self, work_apps: frozenset[str] = frozenset({"code", "code-insiders", "pycharm", "idea", "devenv", "cursor"})) -> None:
        self.work_apps = work_apps
        self._override: str | None = None

    def set_override(self, mode: str | None) -> ModeState:
        if mode not in {None, "companion", "work"}:
            raise ValueError("mode must be companion, work, or None")
        self._override = mode
        return self.state("")

    def state(self, foreground_app: str) -> ModeState:
        if self._override is not None:
            return ModeState(self._override, "manual", self._override)
        mode = "work" if foreground_app.casefold() in self.work_apps else "companion"
        return ModeState(mode, "automatic", None)
