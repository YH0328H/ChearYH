"""Cancellable short acknowledgements for the foreground conversation path."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BackchannelConfig:
    """Rule-based acknowledgements used before an explicit model response."""

    rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (("谢谢", "感谢"), "嗯，收到。"),
        (("难过", "伤心", "糟糕"), "我在听。"),
        (("你好", "嗨", "早上好"), "嗨。"),
        (("?", "？"), "我想一下。"),
    )

    def __post_init__(self) -> None:
        if any(not terms or not utterance.strip() for terms, utterance in self.rules):
            raise ValueError("backchannel rules require terms and non-empty utterances")


@dataclass
class BackchannelHandle:
    """Cancellation signal passed to an output adapter before it queues speech."""

    text: str
    cancelled: threading.Event

    def may_enqueue_tts(self) -> bool:
        """Return false once the full response takes foreground ownership."""
        return not self.cancelled.is_set()

    def cancel(self) -> None:
        self.cancelled.set()


class BackchannelScheduler:
    """Schedule one rule acknowledgement without blocking the conversation thread."""

    def __init__(self, deliver: Callable[[BackchannelHandle], None], config: BackchannelConfig = BackchannelConfig()) -> None:
        self.deliver = deliver
        self.config = config

    def start(self, user_text: str) -> BackchannelHandle | None:
        """Return immediately; adapters must check the handle before TTS enqueue."""
        def matches(term: str) -> bool:
            if term in {"?", "？"}:
                return user_text.rstrip().endswith(term)
            return term.casefold() in user_text.casefold()

        match = next((utterance for terms, utterance in self.config.rules if any(matches(term) for term in terms)), None)
        if match is None:
            return None
        handle = BackchannelHandle(match, threading.Event())
        thread = threading.Thread(target=self._deliver_if_current, args=(handle,), name="cether-backchannel", daemon=True)
        thread.start()
        return handle

    def _deliver_if_current(self, handle: BackchannelHandle) -> None:
        if handle.may_enqueue_tts():
            self.deliver(handle)
