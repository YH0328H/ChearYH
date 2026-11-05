"""Six-feature binary encoding and repeat-hit penalty (TASK.md 14/7.2).

六位特征编码：对每条记忆沿 6 个显式语义维度二值化（0/1），拼成一个 6 位编码
（64 种取值）。编码完全由维度判定函数决定，禁止使用随机哈希代替语义判定
（TASK.md 14：“6 个语义维度显式二值化；禁止随机哈希”）。

当检索结果中连续出现相同编码的记忆时，按递减系数施加惩罚，抑制“千篇一律”
的召回结果霸占注意力（TASK.md 80：“融合后乘以……六位编码惩罚”）。维度判定
函数与惩罚系数均可配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# 六个语义维度名称，顺序即编码位序（bit 0 = 第一个维度 ... bit 5 = 第六个维度）。
# 维度选取基于项目已有的状态/记忆模型，避免凭空发明无法解释的新概念：
# - valence_positive: 情绪效价是否为正（对应 multipliers.py 的 valence_bias 输入）
# - high_salience: 感知显著性是否达到高档（对应 TASK.md 293 的 L1 触发条件之一）
# - high_emotion: 情绪强度是否达到高档（同上）
# - relation_event: 是否关联关系事件（对应 TASK.md 293）
# - self_initiated: 是否由角色自己发起（而非回应用户）
# - flash_weight: 是否为闪光灯（高权重）记忆
DIMENSION_NAMES: tuple[str, ...] = (
    "valence_positive",
    "high_salience",
    "high_emotion",
    "relation_event",
    "self_initiated",
    "flash_weight",
)

DimensionFn = Callable[[dict], bool]


@dataclass(frozen=True)
class HexbitConfig:
    """六位编码惩罚配置。"""

    # 连续命中同编码时的递减系数：第 n 次连续命中（n>=1）惩罚为 decay_factor ** (n-1)。
    decay_factor: float = 0.85
    # 连续命中计数的最小触发阈值：从第几次连续命中开始施加惩罚（1 = 第二次重复即惩罚）。
    min_repeat_to_penalize: int = 1


def encode_six_bits(features: dict, dimension_fns: dict[str, DimensionFn] | None = None) -> int:
    """按 6 个显式语义维度对一条记忆特征字典编码为 0-63 的整数。

    Args:
        features: 记忆的特征字典，键至少覆盖维度判定函数需要的字段
        dimension_fns: 维度名→判定函数的映射；缺省使用 `default_dimension_fns()`

    Returns:
        0-63 之间的整数，bit i 对应 DIMENSION_NAMES[i]
    """
    fns = dimension_fns or default_dimension_fns()
    code = 0
    for i, name in enumerate(DIMENSION_NAMES):
        fn = fns[name]
        if fn(features):
            code |= 1 << i
    return code


def default_dimension_fns() -> dict[str, DimensionFn]:
    """六个维度的默认判定函数，均为显式语义规则，不含随机性。"""
    return {
        "valence_positive": lambda f: f.get("valence", 0.0) > 0.0,
        "high_salience": lambda f: f.get("salience", 0.0) >= f.get("salience_threshold", 0.7),
        "high_emotion": lambda f: f.get("emotion", 0.0) >= f.get("emotion_threshold", 0.7),
        "relation_event": lambda f: bool(f.get("relation_event", False)),
        "self_initiated": lambda f: bool(f.get("self_initiated", False)),
        "flash_weight": lambda f: bool(f.get("flash_weight", False)),
    }


@dataclass(frozen=True)
class EncodedResult:
    """一条检索结果附带其六位编码。"""

    doc_id: str
    score: float
    code: int


def apply_hexbit_penalty(
    results: list[EncodedResult], config: HexbitConfig | None = None
) -> list[EncodedResult]:
    """对连续相同编码的结果施加递减惩罚（TASK.md 80：六位编码惩罚）。

    结果列表按输入顺序（即检索排序）处理：维护“当前连续相同编码计数”，
    一旦编码与前一条不同则计数重置为 0。计数达到 `min_repeat_to_penalize`
    及以上时，当前结果分数乘以 `decay_factor ** repeat_count`。

    Args:
        results: 按排序顺序排列的检索结果，每条已附带六位编码
        config: 惩罚配置，缺省使用预设值

    Returns:
        分数被惩罚系数调整后的新结果列表（顺序不变，供上层重新排序）
    """
    cfg = config or HexbitConfig()
    if not results:
        return []

    adjusted: list[EncodedResult] = []
    repeat_count = 0
    prev_code: int | None = None

    for item in results:
        if prev_code is not None and item.code == prev_code:
            repeat_count += 1
        else:
            repeat_count = 0
        prev_code = item.code

        if repeat_count >= cfg.min_repeat_to_penalize:
            penalty = cfg.decay_factor ** repeat_count
            adjusted.append(EncodedResult(doc_id=item.doc_id, score=item.score * penalty, code=item.code))
        else:
            adjusted.append(item)

    return adjusted
