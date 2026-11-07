"""Retrieval score adjustment: multiplier bias (lifecycle, rumination, drive, valence, region, jitter).

Final score = (RRF score) × lifecycle × rumination_suppression × drive_bias × valence_bias × region_bonus × jitter

All multipliers are configurable and can be hot-reloaded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class MultiplierConfig:
    """Configurable multipliers for retrieval score adjustment."""
    lifecycle_min: float = 0.5  # Minimum lifecycle multiplier (old memories)
    lifecycle_max: float = 1.0  # Maximum lifecycle multiplier (fresh memories)
    rumination_threshold: int = 5  # Recall count threshold within window
    rumination_penalty: float = 0.6  # Penalty for over-recalled memories
    jitter_range: float = 0.1  # Random jitter range ±10%
    region_bonus: float = 1.2  # Bonus for in-region memories (placeholder)


def lifecycle_multiplier(elapsed_seconds: float, tau: float = 86400 * 7, min_mult: float = 0.5) -> float:
    """Lifecycle multiplier: recent memories score higher.

    multiplier = min_mult + (1 - min_mult) * exp(-t/τ)

    Args:
        elapsed_seconds: Time since memory creation
        tau: Time constant (default 7 days)
        min_mult: Minimum multiplier for old memories (default 0.5)

    Returns:
        Multiplier in range [min_mult, 1.0]
    """
    import math
    decay = math.exp(-elapsed_seconds / tau)
    return min_mult + (1.0 - min_mult) * decay


def rumination_suppression(recall_count: int, threshold: int = 5, penalty: float = 0.6) -> float:
    """Rumination suppression: penalize over-recalled memories.

    If a memory was recalled too many times in a short window, reduce its score
    to prevent obsessive focus on the same content.

    Args:
        recall_count: Number of times recalled in recent window (e.g., 7 days)
        threshold: Count threshold to trigger suppression
        penalty: Multiplier when suppressed (0.6 = 40% penalty)

    Returns:
        Multiplier (1.0 if not suppressed, penalty if suppressed)
    """
    return penalty if recall_count >= threshold else 1.0


def drive_bias(memory_tags: list[str], active_drives: dict[str, float], tag_drive_map: dict[str, str]) -> float:
    """Drive bias: boost memories related to active drives.

    Example: if SEEKING drive is high, memories tagged "curiosity" or "exploration" get boosted.

    Args:
        memory_tags: Tags of the memory (e.g., ["curiosity", "user"])
        active_drives: Current drive levels (e.g., {"seeking": 0.8, "affiliation": 0.5})
        tag_drive_map: Mapping from memory tag to drive name (e.g., {"curiosity": "seeking"})

    Returns:
        Multiplier (1.0 baseline, higher if drive is active)
    """
    total_boost = 1.0
    for tag in memory_tags:
        drive_name = tag_drive_map.get(tag)
        if drive_name and drive_name in active_drives:
            # Boost = 1 + drive_level (so 0.8 drive → 1.8x multiplier)
            total_boost += active_drives[drive_name]
    return total_boost


def valence_bias(memory_valence: float, current_valence: float, alignment_boost: float = 1.5) -> float:
    """Valence bias: boost memories with similar emotional valence to current state.

    Args:
        memory_valence: Emotional valence of the memory (-1.0 to 1.0, negative=bad, positive=good)
        current_valence: Current emotional valence (-1.0 to 1.0)
        alignment_boost: Multiplier when valences align (default 1.5)

    Returns:
        Multiplier (higher if valences are similar)
    """
    # Similarity = 1 - abs(diff) / 2, scaled to [0, 1]
    similarity = 1.0 - abs(memory_valence - current_valence) / 2.0
    # Boost aligned memories
    return 1.0 + similarity * (alignment_boost - 1.0)


def region_bonus(memory_region: str | None, current_region: str | None, bonus: float = 1.2) -> float:
    """Region bonus: boost memories from the same spatial/conceptual region.

    This is a placeholder for future spatial indexing (room/stake model).

    Args:
        memory_region: Region tag of the memory (e.g., "work", "home")
        current_region: Current region (e.g., "work")
        bonus: Multiplier when regions match

    Returns:
        Multiplier (bonus if match, 1.0 otherwise)
    """
    if memory_region and current_region and memory_region == current_region:
        return bonus
    return 1.0


def jitter(jitter_range: float = 0.1) -> float:
    """Random jitter: small random perturbation to prevent deterministic ranking.

    Args:
        jitter_range: Range of jitter (±10% by default)

    Returns:
        Random multiplier in [1-range, 1+range]
    """
    return 1.0 + random.uniform(-jitter_range, jitter_range)


def apply_multipliers(
    base_score: float,
    elapsed_seconds: float,
    recall_count: int,
    memory_tags: list[str],
    active_drives: dict[str, float],
    tag_drive_map: dict[str, str],
    memory_valence: float,
    current_valence: float,
    memory_region: str | None,
    current_region: str | None,
    config: MultiplierConfig,
    lifecycle_tau: float = 86400 * 7,
) -> float:
    """Apply all multipliers to a retrieval score.

    Final score = base × lifecycle × rumination × drive × valence × region × jitter

    Args:
        base_score: RRF fusion score
        elapsed_seconds: Time since memory creation
        recall_count: Recent recall count
        memory_tags: Memory tags
        active_drives: Current drive levels
        tag_drive_map: Tag to drive mapping
        memory_valence: Memory emotional valence
        current_valence: Current emotional valence
        memory_region: Memory region tag
        current_region: Current region
        config: Multiplier configuration

    Returns:
        Adjusted score
    """
    score = base_score
    score *= lifecycle_multiplier(elapsed_seconds, tau=lifecycle_tau, min_mult=config.lifecycle_min)
    score *= rumination_suppression(recall_count, config.rumination_threshold, config.rumination_penalty)
    score *= drive_bias(memory_tags, active_drives, tag_drive_map)
    score *= valence_bias(memory_valence, current_valence)
    score *= region_bonus(memory_region, current_region, config.region_bonus)
    score *= jitter(config.jitter_range)
    return score
