"""Born rule sampling for idle action selection (TASK.md 168/486: 借鉴机制).

玻恩规则（Born rule）：量子态 |ψ⟩ = Σ c_i |i⟩ 测量时，测到态 |i⟩ 的概率为 |c_i|²。
对齐 genpark-quantum-measurement-born-rule-sampler-skill 机制，用概率振幅
建模"空闲动作"概率分布：每个可选动作对应一个复振幅，振幅模平方归一化为概率。

空闲动作包括但不限于：看书、发呆、搭话、听音乐、整理物品（对应 ALGORITHMS.md
"玻恩规则抽样：概率振幅计算空闲动作分布（看书/发呆/搭话）"）。

振幅可由当前状态（四意愿、关系张力、此刻情绪）投影得出，避免编造不可解释
的"量子哈密顿"。这里给出通用框架与默认投影函数，角色卡可覆盖或扩展。
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionAmplitude:
    """一个可选空闲动作及其复振幅（以模与相位表示）。"""

    name: str
    magnitude: float  # 振幅模 |c|，非负
    phase: float = 0.0  # 振幅相位 θ（弧度），c = magnitude * exp(i * phase)


@dataclass(frozen=True)
class BornRuleConfig:
    """玻恩规则抽样配置，预留扩展参数槽位。"""

    min_probability_threshold: float = 0.01  # 概率低于该值的动作不参与抽样（避免浮点噪声）


def born_probabilities(amplitudes: list[ActionAmplitude]) -> dict[str, float]:
    """按玻恩规则将振幅列表转为概率分布：P(i) = |c_i|² / Σ|c_j|²。

    相位信息在单次投影测量时不直接影响概率，仅当多个振幅干涉时才体现；
    本简化实现仅使用模，不做复数相干叠加（预留 phase 字段供未来干涉扩展）。
    """
    total = sum(a.magnitude**2 for a in amplitudes)
    if total == 0.0:
        # 全零振幅：均分概率作为兜底（避免除零，保证总有动作可选）
        return {a.name: 1.0 / len(amplitudes) for a in amplitudes} if amplitudes else {}
    return {a.name: (a.magnitude**2) / total for a in amplitudes}


def sample_action(
    amplitudes: list[ActionAmplitude], rng: random.Random | None = None, config: BornRuleConfig | None = None
) -> str | None:
    """按玻恩规则从空闲动作列表中抽样一个动作。

    Args:
        amplitudes: 候选动作及其振幅
        rng: 随机数生成器，缺省使用全局 random
        config: 配置，缺省使用预设值

    Returns:
        被抽中的动作名称；若全部概率低于阈值则返回 None（无可选动作）
    """
    cfg = config or BornRuleConfig()
    rng = rng or random.Random()

    probs = born_probabilities(amplitudes)
    # 过滤低于阈值的动作
    filtered = [(name, p) for name, p in probs.items() if p >= cfg.min_probability_threshold]
    if not filtered:
        return None

    # 重归一化过滤后的概率
    total_filtered = sum(p for _, p in filtered)
    normalized = [(name, p / total_filtered) for name, p in filtered]

    # 累积概率轮盘抽样
    cumulative = 0.0
    r = rng.random()
    for name, p in normalized:
        cumulative += p
        if r <= cumulative:
            return name

    # 浮点误差兜底：返回最后一个
    return normalized[-1][0] if normalized else None


def default_idle_amplitudes(
    social_battery: float, connection_desire: float, expression_impulse: float
) -> list[ActionAmplitude]:
    """从当前状态投影得出默认空闲动作振幅。

    投影规则：
    - 看书：电量中高 + 连接渴望低（独处型）
    - 发呆：电量低或冲动低（静止型）
    - 搭话：连接渴望高 + 表达冲动高（社交型）

    振幅模由对应状态分量加权组合得出，确保语义可解释、可复算。
    """
    # 电量与独处倾向正相关，连接渴望负相关
    read_mag = max(0.0, social_battery * 0.6 + (1.0 - connection_desire) * 0.4)
    # 电量低或冲动低都倾向发呆
    daze_mag = max(0.0, (1.0 - social_battery) * 0.5 + (1.0 - expression_impulse) * 0.5)
    # 连接渴望与表达冲动双高驱动搭话
    chat_mag = max(0.0, connection_desire * 0.6 + expression_impulse * 0.4)

    return [
        ActionAmplitude(name="看书", magnitude=read_mag),
        ActionAmplitude(name="发呆", magnitude=daze_mag),
        ActionAmplitude(name="搭话", magnitude=chat_mag),
    ]
