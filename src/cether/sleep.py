"""Deterministic, role-local sleep consolidation and reflection."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .l0 import L0Archive
from .l1 import L1Archive, L1Record
from .retrieval import Document, BM25
from .roles import RoleContext, RoleRegistry


@dataclass(frozen=True)
class SleepConfig:
    max_records: int = 2000
    duplicate_similarity: float = 0.8
    reflect_min_records: int = 3
    baseline_alpha: float = 0.1
    retrieval_bias_default: float = 1.0

    def __post_init__(self) -> None:
        if self.max_records < 1 or not 0 <= self.duplicate_similarity <= 1:
            raise ValueError("invalid sleep consolidation limits")
        if self.reflect_min_records < 1 or not 0 <= self.baseline_alpha <= 1:
            raise ValueError("invalid reflection configuration")
        if self.retrieval_bias_default <= 0:
            raise ValueError("retrieval_bias_default must be positive")


def load_sleep_config(path: Path) -> SleepConfig:
    """Load validated sleep defaults from TOML."""
    raw = tomllib.loads(path.read_text(encoding="utf-8")).get("sleep", {})
    return SleepConfig(**raw)


class SleepService:
    """Consolidate one active role's L0 and derive traceable deep-sleep products."""

    def __init__(
        self,
        role: RoleContext,
        registry: RoleRegistry,
        *,
        config: SleepConfig = SleepConfig(),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        index_update: Callable[[RoleContext, list[str]], Any] | None = None,
    ) -> None:
        self.role = role
        self.registry = registry
        self.config = config
        self.clock = clock
        self.index_update = index_update or (lambda _role, _candidate_ids: None)
        self.l0 = L0Archive(role.workspace / "memory" / "l0.jsonl")
        self.l1 = L1Archive(role.workspace / "memory" / "l1.jsonl")
        self._last_candidates: list[str] = []

    def consolidate(self, role: RoleContext, state: dict[str, Any]) -> dict[str, Any]:
        """Deduplicate recent L0 candidates and update the role-local index.

        L0 is append-only; this stage returns selected IDs instead of rewriting
        source records. The injected index updater receives this exact set.
        """
        self._check_role(role)
        records = list(self.l0)
        recent = records[-self.config.max_records:]
        kept = self._deduplicate(recent)
        candidate_ids = [str(record["id"]) for record in kept]
        self._last_candidates = candidate_ids
        return {"mode": "light", "records_seen": len(records), "distinct_records": len(kept),
                "candidate_ids": candidate_ids,
                "index_update": self.index_update(self.role, candidate_ids)}

    def refresh_retrieval_bias(self, role: RoleContext, state: dict[str, Any]) -> dict[str, float]:
        """Return stable retrieval-bias factors after the retrieval index refresh."""
        self._check_role(role)
        return {"recent": self.config.retrieval_bias_default,
                "repeated": min(2.0, self.config.retrieval_bias_default + 0.1),
                "indexed_candidates": float(len(self._last_candidates))}

    def reflect(self, role: RoleContext, state: dict[str, Any]) -> dict[str, Any]:
        self._check_role(role)
        records = [record for record in self.l0 if str(record.get("text", "")).strip()]
        if len(records) < self.config.reflect_min_records:
            return {"baseline": {}, "retrieval_bias": {}, "narrative": None,
                    "records_used": len(records)}
        recent = records[-self.config.max_records:]
        texts = [str(item["text"]).strip() for item in recent]
        summary = self._extractive_summary(texts)
        source_ids = [str(item["id"]) for item in recent[-3:]]
        baseline = self._calibrate_baseline(state, texts)
        retrieval_bias = self.refresh_retrieval_bias(role, state)
        narrative = f"反思：{summary}"
        return {"baseline": baseline, "retrieval_bias": retrieval_bias,
                "narrative": narrative, "records_used": len(recent),
                "source_l0_ids": source_ids}

    def deep_sleep(self, role: RoleContext, state: dict[str, Any]) -> dict[str, Any]:
        """Create a reproducible dream fragment from role-local low-weight records."""
        self._check_role(role)
        candidates = [item for item in self.l0 if item.get("weight") == "low" and str(item.get("text", "")).strip()]
        if len(candidates) < self.config.reflect_min_records:
            return {"dream": None, "source_l0_ids": []}
        # Stable selection makes products reproducible across restarts for the same archive.
        selected = candidates[-min(3, len(candidates)):]
        fragments = [str(item["text"]).strip() for item in selected]
        dream = "梦境片段（由低权重记忆拼接）：" + "；".join(fragments)
        ids = [str(item["id"]) for item in selected]
        self.l1.append(L1Record(self.clock(), dream, "dream", "self", ids))
        return {"dream": dream, "source_l0_ids": ids}

    def _check_role(self, role: RoleContext) -> None:
        self.registry.ensure_role_scope(role.scope_id)
        if role.scope_id != self.role.scope_id:
            raise ValueError("sleep service role scope mismatch")

    def _deduplicate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for record in records:
            text = str(record.get("text", "")).strip()
            if not text:
                continue
            tokens = set(text.casefold().split())
            duplicate = False
            for prior in kept:
                other = set(str(prior.get("text", "")).casefold().split())
                similarity = len(tokens & other) / max(1, len(tokens | other))
                if similarity >= self.config.duplicate_similarity:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(record)
        return kept

    @staticmethod
    def _extractive_summary(texts: list[str]) -> str:
        documents = [Document(str(index), text, text.casefold().split()) for index, text in enumerate(texts)]
        ranked = BM25(documents).search(" ".join(texts).casefold().split(), top_k=min(3, len(texts)))
        selected = [texts[int(result.doc_id)] for result in ranked]
        return "；".join(selected)

    def _calibrate_baseline(self, state: dict[str, Any], texts: list[str]) -> dict[str, float]:
        baseline_keys = [key for key in state if key.endswith("_baseline")]
        if not baseline_keys:
            return {}
        observations = {key: sum(1 for text in texts if key.removesuffix("_baseline").replace("_", " ") in text.casefold()) / len(texts)
                       for key in baseline_keys}
        return {key: (1 - self.config.baseline_alpha) * _unit(state.get(key, 0.5)) +
                     self.config.baseline_alpha * observations[key] for key in baseline_keys}


def _unit(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5
