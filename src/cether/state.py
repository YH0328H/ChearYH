"""State evolution: surprise, inertial filtering, four-will projection, texture translation.

State dimensions are extensible. Default template provides four-will (social battery,
connection desire, expression impulse, security), but role cards can customize dimensions.

State→behavior mapping is injected via persona prompts, not hardcoded logic.

Theoretical foundations:
- PSI theory (Dörner): activation, competence, uncertainty resolution, needs (affiliation, certainty)
- SDT (Self-Determination Theory): autonomy, competence, relatedness
- Panksepp's affective systems: SEEKING, CARE, PANIC/GRIEF, PLAY
- The Synthetic Mind: Hull drive theory modernized, intrinsic curiosity (prediction error)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StateSnapshot:
    """One snapshot of the role's internal state."""
    timestamp: float
    dimensions: dict[str, float]  # dimension_name → value (0.0-1.0)


def compute_surprise(new_text: str, recent_texts: list[str]) -> float:
    """Compute surprise score as 1 - average Jaccard similarity.

    Higher surprise → higher initial weight for the new memory.
    Based on intrinsic curiosity (prediction error-driven) from The Synthetic Mind.
    """
    if not recent_texts:
        return 1.0

    def jaccard(a: str, b: str) -> float:
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        if not tokens_a and not tokens_b:
            return 1.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return intersection / union if union > 0 else 0.0

    similarities = [jaccard(new_text, old) for old in recent_texts]
    avg_similarity = sum(similarities) / len(similarities)
    return 1.0 - avg_similarity


def inertial_filter(current: float, target: float, alpha: float = 0.7) -> float:
    """First-order inertial filter: smooth state transitions.

    v_t = alpha * v_{t-1} + (1-alpha) * v_target

    Args:
        current: Current state value
        target: Target state value
        alpha: Inertia coefficient (0.7=slow, 0.3=fast)

    Returns:
        New state value after one step
    """
    return alpha * current + (1.0 - alpha) * target


@dataclass
class SixDrives:
    """Six core drives inspired by PSI, SDT, Panksepp, and The Synthetic Mind.

    Each drive ranges 0.0-1.0 and represents a motivational force.
    """
    seeking: float = 0.5  # SEEKING (Panksepp): exploration, curiosity, anticipation
    affiliation: float = 0.5  # PSI affiliation + SDT relatedness: need for connection
    competence: float = 0.5  # PSI competence + SDT competence: need for mastery and effectiveness
    certainty: float = 0.5  # PSI uncertainty resolution: need for predictability and control
    care: float = 0.5  # CARE (Panksepp): nurturing, empathy, protective impulse
    play: float = 0.5  # PLAY (Panksepp): joy, lightness, social engagement without stakes


@dataclass
class FourWill:
    """Default four-will template: social battery, connection desire, expression impulse, security.

    Projected from six drives via weighted mapping inspired by PSI/SDT/Panksepp integration.
    """
    social_battery: float  # 0.0-1.0, depleted by expression, restored by rest (energy/activation)
    connection_desire: float  # 0.0-1.0, want to be close (affiliation + care)
    expression_impulse: float  # 0.0-1.0, want to speak (seeking + competence)
    security: float  # 0.0-1.0, feel safe (certainty + inverse of uncertainty)


def project_six_drives_to_four_will(drives: SixDrives, social_battery_current: float = 0.8) -> FourWill:
    """Project six-dimension drives to four-will via weighted mapping.

    Mapping inspired by PSI/SDT/Panksepp integration:
    - social_battery: maintained separately (energy/activation level, not derived from drives)
    - connection_desire: affiliation (primary) + care (secondary)
    - expression_impulse: seeking (exploration) + competence (mastery) + play (lightness)
    - security: certainty (predictability) - seeking (novelty inversely correlates with safety)

    Args:
        drives: Six-dimensional drive state
        social_battery_current: Current energy level (maintained separately)

    Returns:
        Four-will projection
    """
    return FourWill(
        social_battery=social_battery_current,  # Passed in, not computed from drives
        connection_desire=drives.affiliation * 0.7 + drives.care * 0.3,
        expression_impulse=drives.seeking * 0.4 + drives.competence * 0.4 + drives.play * 0.2,
        security=drives.certainty * 0.8 - drives.seeking * 0.2,  # High seeking reduces security
    )


def translate_to_texture(dimension: str, value: float) -> str:
    """Translate numeric state to natural language texture.

    This is a simple template-based translator. Production version should use
    LLM generation or richer template library.
    """
    if dimension == "social_battery":
        if value > 0.7:
            return "精力充沛，愿意多聊"
        elif value > 0.4:
            return "还行，可以聊"
        elif value > 0.2:
            return "有点累了"
        else:
            return "累得不想说话，但又在等你"
    elif dimension == "connection_desire":
        if value > 0.7:
            return "很想跟你说话"
        elif value > 0.4:
            return "想聊聊"
        else:
            return "不太想聊"
    elif dimension == "expression_impulse":
        if value > 0.7:
            return "有很多话想说"
        elif value > 0.4:
            return "有些想法"
        else:
            return "不知道说什么"
    elif dimension == "security":
        if value > 0.7:
            return "感觉很安全"
        elif value > 0.4:
            return "还好"
        else:
            return "有点不安"
    else:
        return f"{dimension}={value:.2f}"

