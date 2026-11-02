"""Memory finalization: dialogue channel calls finalization tool, system intercepts and writes to hot store.

Fallback strategy (4.13) when dialogue channel does not call the tool:
- discard: drop the candidate
- downgrade: write to L0 via backend
- keep: leave in candidate pool

No runtime randomization allowed.
"""

from __future__ import annotations

from enum import Enum


class FallbackStrategy(Enum):
    """What to do when dialogue channel does not call finalization tool (4.13)."""
    DISCARD = "discard"
    DOWNGRADE = "downgrade"
    KEEP = "keep"


class FinalizationDecision:
    """Decision on whether a candidate should enter L1."""
    def __init__(self, approved: bool, reason: str) -> None:
        self.approved = approved
        self.reason = reason


def decide_finalization(narrative: str, emotion_tag: str | None, relation_tag: str | None) -> FinalizationDecision:
    """Decide if a candidate should be finalized into L1. Returns approval and reason."""
    # Basic validation: narrative must not be empty
    if not narrative or not narrative.strip():
        return FinalizationDecision(False, "empty narrative")

    # Emotion tag validation: must be non-empty if present
    if emotion_tag is not None and not emotion_tag.strip():
        return FinalizationDecision(False, "empty emotion tag")

    # Relation tag validation: must be non-empty if present
    if relation_tag is not None and not relation_tag.strip():
        return FinalizationDecision(False, "empty relation tag")

    # Approved by default if basic validation passes
    return FinalizationDecision(True, "approved")


def apply_fallback(strategy: FallbackStrategy) -> str:
    """Return the action to take based on fallback strategy."""
    if strategy == FallbackStrategy.DISCARD:
        return "discard"
    elif strategy == FallbackStrategy.DOWNGRADE:
        return "downgrade_to_l0"
    elif strategy == FallbackStrategy.KEEP:
        return "keep_in_pool"
    else:
        raise ValueError(f"unknown fallback strategy: {strategy}")
