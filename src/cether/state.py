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


@dataclass(frozen=True)
class AffectProjection:
    """Ephemeral valence/arousal projection for one event and relation context.

    Values are derived on demand; they are not persisted as independent state dimensions.
    """

    valence: float
    arousal: float


def project_affect(momentary_valence: float, relation_tension: float) -> AffectProjection:
    """Project event valence and relation tension into bounded affect semantics.

    Valence preserves the current emotion's positive/negative direction. Arousal
    combines emotional magnitude with relationship tension, so either an intense
    emotion or a tense interaction can activate the moment without changing its
    direction. Inputs are clamped to the documented ranges.
    """
    if not -1.0 <= momentary_valence <= 1.0:
        raise ValueError("momentary_valence must be between -1.0 and 1.0")
    if not 0.0 <= relation_tension <= 1.0:
        raise ValueError("relation_tension must be between 0.0 and 1.0")
    return AffectProjection(
        valence=momentary_valence,
        arousal=abs(momentary_valence) * 0.7 + relation_tension * 0.3,
    )


def penetration_eligible(
    *,
    enabled: bool,
    momentary_valence: float,
    relation_tension: float,
    arousal_threshold: float = 0.7,
    valence_threshold: float = 0.25,
) -> bool:
    """Require configured penetration, strong arousal, and a clear valence direction."""
    if not 0.0 <= arousal_threshold <= 1.0:
        raise ValueError("arousal_threshold must be between 0.0 and 1.0")
    if not 0.0 <= valence_threshold <= 1.0:
        raise ValueError("valence_threshold must be between 0.0 and 1.0")
    affect = project_affect(momentary_valence, relation_tension)
    return enabled and affect.arousal >= arousal_threshold and abs(affect.valence) >= valence_threshold


@dataclass(frozen=True)
class TensionStateConfig:
    """张力态区间判定阈值（TASK.md 60/227：张力态自然涌现）。

    张力态不是新增状态变量，而是四意愿（FourWill）与关系张力、此刻情绪
    （valence）在数值区间上的组合判定（对齐 TASK.md 279）。每个阈值可
    独立配置，便于不同角色卡调出不同的"敏感度"。
    """

    close_but_afraid_connection_min: float = 0.7  # 想靠近但不敢：连接渴望下限
    close_but_afraid_security_max: float = 0.4    # 想靠近但不敢：安全感上限
    tired_but_reluctant_battery_max: float = 0.3  # 累了但舍不得走：社交电量上限
    tired_but_reluctant_connection_min: float = 0.6  # 累了但舍不得走：连接渴望下限
    afraid_to_speak_impulse_min: float = 0.6      # 想说话但怕说错：表达冲动下限
    afraid_to_speak_security_max: float = 0.4     # 想说话但怕说错：安全感上限
    disappointed_impulse_min: float = 0.6         # 期待但失望：表达冲动（代理期待）下限
    disappointed_valence_max: float = -0.2        # 期待但失望：此刻情绪效价上限


@dataclass(frozen=True)
class TensionStateHit:
    """单个张力态命中记录，含触发它的具体数值（可观测、可复算）。"""

    name: str
    description: str
    evidence: dict[str, float]


def detect_tension_state(
    will: FourWill,
    relation_tension: float,
    momentary_valence: float,
    config: TensionStateConfig | None = None,
) -> list[TensionStateHit]:
    """张力态自然涌现：由四意愿 + 关系张力 + 此刻情绪投影得出，不新增状态变量。

    覆盖 TASK.md 60 要求的至少四种张力态：
    - 想靠近但不敢：connection_desire 高 且 security 低
    - 累了但舍不得走：social_battery 低 且 connection_desire 高
    - 想说话但怕说错：expression_impulse 高 且 security 低
    - 期待但失望：expression_impulse 高（代理"期待"）且 此刻情绪效价低（失望）

    `relation_tension`（0.0-1.0，关系张力，中变层）目前作为所有判定的
    共同抑制性前提：关系张力过低时（双方关系松弛），矛盾态不易涌现；
    该参数预留给未来按张力强度调节触发概率/强度，当前版本仅记录在
    evidence 中供检索偏置与可观测性使用，不参与阈值判定本身，避免在
    未取得真实关系张力分布前引入不可验证的新阈值（遵循 ARCHITECTURE.md
    “参数预设化不因调参停滞进度”，暂缺的交互假设留空而非编造）。

    Args:
        will: 当前四意愿投影结果
        relation_tension: 关系张力（中变层，0.0-1.0）
        momentary_valence: 此刻情绪效价（快变层，-1.0 到 1.0）
        config: 区间阈值配置，缺省使用预设值

    Returns:
        命中的张力态列表，每项含触发证据（用于验收 TASK.md 227 的数值推演记录）
    """
    cfg = config or TensionStateConfig()
    hits: list[TensionStateHit] = []

    if (
        will.connection_desire >= cfg.close_but_afraid_connection_min
        and will.security <= cfg.close_but_afraid_security_max
    ):
        hits.append(
            TensionStateHit(
                name="想靠近但不敢",
                description="连接渴望高但安全感低：想靠近又怕受伤",
                evidence={
                    "connection_desire": will.connection_desire,
                    "security": will.security,
                    "relation_tension": relation_tension,
                },
            )
        )

    if (
        will.social_battery <= cfg.tired_but_reluctant_battery_max
        and will.connection_desire >= cfg.tired_but_reluctant_connection_min
    ):
        hits.append(
            TensionStateHit(
                name="累了但舍不得走",
                description="社交电量低但连接渴望高：累却不想结束这段陪伴",
                evidence={
                    "social_battery": will.social_battery,
                    "connection_desire": will.connection_desire,
                    "relation_tension": relation_tension,
                },
            )
        )

    if (
        will.expression_impulse >= cfg.afraid_to_speak_impulse_min
        and will.security <= cfg.afraid_to_speak_security_max
    ):
        hits.append(
            TensionStateHit(
                name="想说话但怕说错",
                description="表达冲动高但安全感低：有话想说又怕说错惹麻烦",
                evidence={
                    "expression_impulse": will.expression_impulse,
                    "security": will.security,
                    "relation_tension": relation_tension,
                },
            )
        )

    if (
        will.expression_impulse >= cfg.disappointed_impulse_min
        and momentary_valence <= cfg.disappointed_valence_max
    ):
        hits.append(
            TensionStateHit(
                name="期待但失望",
                description="表达冲动高（曾有期待）但此刻情绪效价低：期待落空后的失落",
                evidence={
                    "expression_impulse": will.expression_impulse,
                    "momentary_valence": momentary_valence,
                    "relation_tension": relation_tension,
                },
            )
        )

    return hits


def ebbinghaus_decay(initial_weight: float, elapsed_seconds: float, tau: float = 86400 * 7) -> float:
    """Ebbinghaus forgetting curve: exponential decay over time.

    w(t) = w0 * exp(-Δt / τ)

    Args:
        initial_weight: Starting weight (0.0-1.0)
        elapsed_seconds: Time since creation
        tau: Time constant in seconds (default: 7 days = 604800 seconds)
             High-weight memories use larger tau (slower decay)
             Low-weight memories use smaller tau (faster decay)

    Returns:
        Decayed weight
    """
    import math
    return initial_weight * math.exp(-elapsed_seconds / tau)


def weibull_decay(initial_weight: float, elapsed_seconds: float, lambda_param: float = 1.0 / (86400 * 7),
                  k: float = 0.8) -> float:
    """Weibull decay: more flexible than exponential, fast initial decay then gradual.

    w(t) = w0 * exp(-(λt)^k)

    Weibull is preferred over pure Ebbinghaus for realistic forgetting:
    - k < 1: fast initial decay, then slower (matches human memory better)
    - k = 1: reduces to exponential (same as Ebbinghaus)
    - k > 1: slow initial decay, then faster

    Args:
        initial_weight: Starting weight (0.0-1.0)
        elapsed_seconds: Time since creation
        lambda_param: Decay rate parameter (default: 1/week)
        k: Shape parameter (default: 0.8, fast initial decay)

    Returns:
        Decayed weight
    """
    import math
    return initial_weight * math.exp(-((lambda_param * elapsed_seconds) ** k))


