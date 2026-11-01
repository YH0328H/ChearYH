"""Checkpoint flow: drive check -> gate -> hesitation -> hesitation window -> outcome -> mind box.

Each step returns a result instead of calling a model. The caller decides
what to do with the outcome. Hesitation that ends without speaking is written
to the mind box, and it affects the next checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class Outcome(str, Enum):
    BLOCKED = "blocked"              # 驱动检验或闸门未通过，未进入犹豫
    SPOKE = "spoke"                  # 犹豫后回应
    WITHDRAWN = "withdrawn"          # 犹豫后撤回，写入心事匣
    SOFT = "soft"                    # 犹豫后选择轻方式（不开口，记入心事匣）


@dataclass
class MindBox:
    """Append-only list of low-weight notes. Checkpoints read it first."""

    items: list[dict] = field(default_factory=list)

    def add(self, text: str, ts: datetime) -> None:
        self.items.append({"ts": ts.isoformat(), "text": text, "weight": "low"})

    def pending_hesitation(self) -> list[dict]:
        return [i for i in self.items if i.get("kind") == "hesitation"]


@dataclass(frozen=True)
class CheckpointResult:
    outcome: Outcome
    reason: str | None = None
    hesitation_text: str | None = None


def drive_check(expression_impulse: float, threshold: float = 0.5) -> str | None:
    """First step. Return a reason if the expression impulse is too low."""
    if expression_impulse < threshold:
        return "low_impulse"
    return None


def run_checkpoint(
    *,
    now: datetime,
    expression_impulse: float,
    gate_reason: str | None,
    user_responded_within: timedelta | None,
    hesitation_window: timedelta,
    mind_box: MindBox,
    hesitation_text: str,
) -> CheckpointResult:
    """Run one checkpoint. Returns the outcome; does not call a model.

    `user_responded_within` is the time until the user clicked during the
    hesitation window, or None if they did not. Whether a click means speak,
    cancel, or soft is left to the persona. Here the click only counts as a
    reply signal, which matches the spec: no hard-coded meaning.
    """
    reason = drive_check(expression_impulse)
    if reason is not None:
        return CheckpointResult(Outcome.BLOCKED, reason)
    if gate_reason is not None:
        return CheckpointResult(Outcome.BLOCKED, gate_reason)

    # 犹豫必须有可见信号；这里仅记录，由 UI 层展示
    if user_responded_within is not None and user_responded_within <= hesitation_window:
        return CheckpointResult(Outcome.SPOKE, hesitation_text=hesitation_text)

    # 未开口的犹豫必须写入心事匣
    mind_box.items.append(
        {"ts": now.isoformat(), "text": hesitation_text, "weight": "low", "kind": "hesitation"}
    )
    return CheckpointResult(Outcome.WITHDRAWN, hesitation_text=hesitation_text)
