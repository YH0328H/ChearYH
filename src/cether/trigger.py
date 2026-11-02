"""L1 trigger detection: explicit conditions only (4.21).

L1 is written only when:
- Manual mark (user says "让它记住这个")
- Relation event
- High emotion intensity
- High salience
- Short-window repetition (same theme reappears within configurable window)

Otherwise, only L0 is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TriggerConfig:
    """Configurable thresholds for L1 triggers."""
    emotion_high_threshold: float  # e.g. 0.7
    salience_high_threshold: float  # e.g. 0.7
    repetition_window_seconds: float  # e.g. 3600 (1 hour)


@dataclass(frozen=True)
class EventContext:
    """Context for one L0 event to decide if it triggers L1."""
    ts: datetime
    manual_mark: bool
    is_relation_event: bool
    emotion_intensity: float  # 0.0-1.0
    salience: float  # 0.0-1.0
    theme: str | None  # for repetition detection


def should_trigger_l1(ctx: EventContext, cfg: TriggerConfig, recent_themes: list[tuple[datetime, str]]) -> bool:
    """Return True if this event should trigger L1 generation (4.21)."""
    # 1. Manual mark
    if ctx.manual_mark:
        return True
    # 2. Relation event
    if ctx.is_relation_event:
        return True
    # 3. High emotion intensity
    if ctx.emotion_intensity >= cfg.emotion_high_threshold:
        return True
    # 4. High salience
    if ctx.salience >= cfg.salience_high_threshold:
        return True
    # 5. Short-window repetition
    if ctx.theme:
        cutoff = ctx.ts - timedelta(seconds=cfg.repetition_window_seconds)
        for ts, theme in recent_themes:
            if ts >= cutoff and theme == ctx.theme:
                return True
    return False
