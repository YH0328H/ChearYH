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


def drive_check(expression_impulse: float, threshold: float) -> str | None:
    """First step. Return a reason if the expression impulse is too low."""
    if expression_impulse < threshold:
        return "low_impulse"
    return None


def run_checkpoint(
    *,
    now: datetime,
    expression_impulse: float,
    impulse_threshold: float,
    gate_reason: str | None,
    hesitation_resolution: Outcome | None,
    mind_box: MindBox,
    hesitation_text: str,
) -> CheckpointResult:
    """Run one checkpoint. Returns the outcome; does not call a model.

    `hesitation_resolution` is what the persona layer decided during the
    hesitation window: SPOKE, WITHDRAWN, or SOFT, or None if the window ended
    with no decision. This flow does not interpret clicks. Persona and runtime
    own that meaning (spec 10.15.2 and 10.15.3).
    """
    reason = drive_check(expression_impulse, impulse_threshold)
    if reason is not None:
        return CheckpointResult(Outcome.BLOCKED, reason)
    if gate_reason is not None:
        return CheckpointResult(Outcome.BLOCKED, gate_reason)

    if hesitation_resolution == Outcome.SPOKE:
        return CheckpointResult(Outcome.SPOKE, hesitation_text=hesitation_text)

    # 撤回、轻方式、或窗口结束未决定，都视为未开口，必须写入心事匣
    outcome = hesitation_resolution if hesitation_resolution == Outcome.SOFT else Outcome.WITHDRAWN
    mind_box.items.append(
        {"ts": now.isoformat(), "text": hesitation_text, "weight": "low", "kind": "hesitation"}
    )
    return CheckpointResult(outcome, hesitation_text=hesitation_text)
