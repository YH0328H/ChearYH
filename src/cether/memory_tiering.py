"""Deterministic classification of newly archived memory records."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class MemoryTierConfig:
    high_emotion: float = 0.8
    high_salience: float = 0.8
    relation_salience: float = 0.6


def classify_memory_tier(metadata: dict[str, Any], config: MemoryTierConfig = MemoryTierConfig()) -> str:
    """Classify an event as high, normal, or low without model calls."""
    if str(metadata.get("weight", "normal")) == "low":
        return "low"
    if bool(metadata.get("manual_mark")) or bool(metadata.get("flash_weight")):
        return "high"
    emotion = float(metadata.get("emotion_intensity", 0.0))
    salience = float(metadata.get("salience", 0.0))
    relation = bool(metadata.get("is_relation_event"))
    if emotion >= config.high_emotion or salience >= config.high_salience:
        return "high"
    if relation and salience >= config.relation_salience:
        return "high"
    return "normal"
