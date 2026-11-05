"""Context injection budget priority arbitration (TASK.md 新增 7.8).

单轮对话通道注入存在固定预算上限。当候选内容合计超出预算时，必须按
优先级从高到低裁决，绝不允许低优先级内容挤占高优先级内容的预算：

    人格锚点 > 硬边界 > 当前状态质地 > 关系摘要 > 心事匣 > 召回记忆 > 会话续接摘要

同一优先级内部，若仍然超出剩余预算，距当前时间更近的片段优先保留
（TASK.md 7.8：“同级冲突时按时间近者优先”）。裁决过程逐段写入可观测的
`BudgetDecision` 列表，不做静默丢弃。

预算单位统一为字符数（而非 token），因为项目当前未绑定具体分词器；
字符预算是对 token 预算的保守近似，字符数上限天然大于等价 token 上限。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# 优先级顺序：数值越小优先级越高。顺序来自 TASK.md 新增 7.8。
PRIORITY_ORDER: tuple[str, ...] = (
    "persona_anchor",      # 人格锚点
    "hard_boundary",       # 硬边界
    "state_texture",       # 当前状态质地
    "relation_summary",    # 关系摘要
    "mind_box",            # 心事匣
    "recall_memory",       # 召回记忆
    "session_continuation",  # 会话续接摘要
)

_PRIORITY_RANK: dict[str, int] = {name: idx for idx, name in enumerate(PRIORITY_ORDER)}


@dataclass(frozen=True)
class BudgetConfig:
    """各优先级段位的字符预算上限。

    每段预算互不借用：段位各自的上限用尽后，即便其它段位仍有余量，
    该段位也不会从别处借用空间（对齐 TASK.md 10：“固定单轮注入预算：
    人格锚点、关系摘要、召回记忆各有上限，互不借用”）。
    """

    persona_anchor: int = 400
    hard_boundary: int = 200
    state_texture: int = 150
    relation_summary: int = 300
    mind_box: int = 250
    recall_memory: int = 600
    session_continuation: int = 200

    def limit_for(self, category: str) -> int:
        if not hasattr(self, category):
            raise ValueError(f"unknown budget category: {category!r}")
        return int(getattr(self, category))


def load_budget_config(path: Path) -> BudgetConfig:
    """从 TOML 加载，缺失项使用默认值；文件不存在时返回全默认配置。"""
    if not path.exists():
        return BudgetConfig()
    raw = tomllib.loads(path.read_text(encoding="utf-8")).get("context_budget", {})
    defaults = BudgetConfig()
    return BudgetConfig(
        persona_anchor=raw.get("persona_anchor", defaults.persona_anchor),
        hard_boundary=raw.get("hard_boundary", defaults.hard_boundary),
        state_texture=raw.get("state_texture", defaults.state_texture),
        relation_summary=raw.get("relation_summary", defaults.relation_summary),
        mind_box=raw.get("mind_box", defaults.mind_box),
        recall_memory=raw.get("recall_memory", defaults.recall_memory),
        session_continuation=raw.get("session_continuation", defaults.session_continuation),
    )


@dataclass(frozen=True)
class ContextSegment:
    """一段待注入的候选内容。"""

    category: str          # 必须是 PRIORITY_ORDER 中的一个
    text: str
    timestamp: float = 0.0  # 越大表示越新；同优先级内用于裁决顺序

    def __post_init__(self) -> None:
        if self.category not in _PRIORITY_RANK:
            raise ValueError(f"unknown segment category: {self.category!r}")


@dataclass(frozen=True)
class BudgetDecision:
    """单个片段的裁决结果，供可观测性审计使用。"""

    category: str
    kept: bool
    kept_chars: int
    original_chars: int
    reason: str


@dataclass(frozen=True)
class BudgetResult:
    segments: list[ContextSegment] = field(default_factory=list)
    decisions: list[BudgetDecision] = field(default_factory=list)

    def rendered_text(self) -> str:
        """按优先级顺序拼接保留片段的文本（高优先级在前）。"""
        return "\n".join(seg.text for seg in self.segments if seg.text)


def allocate_budget(candidates: list[ContextSegment], config: BudgetConfig) -> BudgetResult:
    """按 TASK.md 7.8 的优先级裁决规则分配预算。

    规则：
    1. 每个 category 维护独立字符预算，互不借用。
    2. 按 PRIORITY_ORDER 从高到低处理；每个 category 内，timestamp 越大
       （越新）越先获得预算。
    3. 片段在其 category 剩余预算内完整保留；超出剩余预算的部分被整段
       裁剪掉（不做字符级截断，保证语义完整，避免半句话注入）。
    4. 低优先级片段永远不会挤占高优先级片段已经占用的预算，因为预算
       按 category 隔离，而非全局共享池。
    """
    decisions: list[BudgetDecision] = []
    kept_segments: list[ContextSegment] = []

    by_category: dict[str, list[ContextSegment]] = {name: [] for name in PRIORITY_ORDER}
    for seg in candidates:
        by_category[seg.category].append(seg)

    for category in PRIORITY_ORDER:
        remaining = config.limit_for(category)
        # 同级按时间近者优先：timestamp 降序。
        ordered = sorted(by_category[category], key=lambda s: s.timestamp, reverse=True)
        for seg in ordered:
            length = len(seg.text)
            if length <= remaining:
                kept_segments.append(seg)
                remaining -= length
                decisions.append(
                    BudgetDecision(
                        category=category,
                        kept=True,
                        kept_chars=length,
                        original_chars=length,
                        reason="within_budget",
                    )
                )
            else:
                decisions.append(
                    BudgetDecision(
                        category=category,
                        kept=False,
                        kept_chars=0,
                        original_chars=length,
                        reason="exceeds_remaining_category_budget",
                    )
                )

    # 输出顺序遵循优先级顺序（而非输入顺序），方便渲染时高优先级内容在前。
    kept_segments.sort(key=lambda s: (_PRIORITY_RANK[s.category], -s.timestamp))
    return BudgetResult(segments=kept_segments, decisions=decisions)
