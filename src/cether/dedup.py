"""Near-duplicate memory merging via Jaccard similarity, with numeric and flash protection.

TASK.md 48/135：实现相似度合并与数字保护——数字不一致时禁止合并；闪光灯
（高权重）节点不参与合并；可选本地实体替换后再调用外部 API（本模块不涉及
外部 API 调用，仅做合并判定）。

合并判定使用 Jaccard 相似度（与 state.py::compute_surprise 同源的词集合
相似度度量，但服务于不同场景：这里用于判定"是否应合并为一条"，惊讶度用于
"新记忆初始权重"）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def jaccard_similarity(a: str, b: str) -> float:
    """词集合 Jaccard 相似度：|交集| / |并集|，与 state.py 的实现保持一致。"""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    union = len(tokens_a | tokens_b)
    if union == 0:
        return 0.0
    return len(tokens_a & tokens_b) / union


def extract_numbers(text: str) -> set[str]:
    """提取文本中出现的所有数字（字符串形式，保留原始写法用于严格比较）。"""
    return set(_NUMBER_PATTERN.findall(text))


def numbers_conflict(a: str, b: str) -> bool:
    """数字保护：两段文本中出现的数字集合不同即视为冲突，禁止合并。

    TASK.md 48：“数字不一致时禁止合并”。例如“21:00到”与“21:30到”词面高度
    相似但语义不同，必须保护，不能被合并抹去差异。
    """
    return extract_numbers(a) != extract_numbers(b)


@dataclass(frozen=True)
class MergeCandidate:
    """一条参与合并判定的记忆片段。"""

    id: str
    text: str
    flash_weight: bool = False  # 闪光灯（高权重）节点：关系事件/高情绪记忆


@dataclass(frozen=True)
class DedupConfig:
    """相似度合并配置。"""

    similarity_threshold: float = 0.8  # Jaccard 相似度达到该值才考虑合并


@dataclass(frozen=True)
class MergeDecision:
    """两条记忆之间的合并判定结果，含拒绝原因（可观测）。"""

    kept_id: str
    dropped_id: str
    similarity: float
    merged: bool
    reason: str


def decide_merge(
    a: MergeCandidate, b: MergeCandidate, config: DedupConfig | None = None
) -> MergeDecision:
    """判定两条记忆是否应合并为一条，保留较早（a）的 id 作为 kept_id。

    规则优先级（TASK.md 48/135）：
    1. 任一方是闪光灯节点 → 禁止合并（闪光灯不参与合并）。
    2. 数字集合不一致 → 禁止合并（数字保护）。
    3. Jaccard 相似度未达阈值 → 不合并。
    4. 否则 → 合并，保留 a。
    """
    cfg = config or DedupConfig()

    if a.flash_weight or b.flash_weight:
        return MergeDecision(
            kept_id=a.id, dropped_id=b.id, similarity=0.0, merged=False, reason="flash_weight_excluded"
        )

    if numbers_conflict(a.text, b.text):
        similarity = jaccard_similarity(a.text, b.text)
        return MergeDecision(
            kept_id=a.id, dropped_id=b.id, similarity=similarity, merged=False, reason="numbers_conflict"
        )

    similarity = jaccard_similarity(a.text, b.text)
    if similarity < cfg.similarity_threshold:
        return MergeDecision(
            kept_id=a.id, dropped_id=b.id, similarity=similarity, merged=False, reason="below_threshold"
        )

    return MergeDecision(kept_id=a.id, dropped_id=b.id, similarity=similarity, merged=True, reason="merged")


def merge_near_duplicates(
    candidates: list[MergeCandidate], config: DedupConfig | None = None
) -> tuple[list[MergeCandidate], list[MergeDecision]]:
    """对一组候选记忆做两两近重合并（保留列表顺序中较早出现的一条）。

    采用贪心策略：按输入顺序遍历，每条新记忆与"已保留集合"中的每一条比较；
    命中合并条件则丢弃该新记忆（保留已在集合中的那条），否则加入保留集合。

    Returns:
        (保留下来的记忆列表, 全部两两判定的决策记录列表（用于可观测审计）)
    """
    cfg = config or DedupConfig()
    kept: list[MergeCandidate] = []
    decisions: list[MergeDecision] = []

    for candidate in candidates:
        merged_away = False
        for existing in kept:
            decision = decide_merge(existing, candidate, cfg)
            decisions.append(decision)
            if decision.merged:
                merged_away = True
                break
        if not merged_away:
            kept.append(candidate)

    return kept, decisions
