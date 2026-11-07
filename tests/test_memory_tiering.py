from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l0 import L0Archive
from cether.memory_tiering import classify_memory_tier


def test_classifies_explicit_high_events_without_model_call() -> None:
    assert classify_memory_tier({"manual_mark": True}) == "high"
    assert classify_memory_tier({"emotion_intensity": 0.9}) == "high"
    assert classify_memory_tier({"is_relation_event": True, "salience": 0.7}) == "high"
    assert classify_memory_tier({"salience": 0.2}) == "normal"
    assert classify_memory_tier({"weight": "low", "emotion_intensity": 1.0}) == "low"


def test_l0_keeps_coarse_weight_and_tier_metadata(tmp_path: Path) -> None:
    archive = L0Archive(tmp_path / "l0.jsonl")
    record_id = archive.append("important", "event", metadata={"memory_tier": "high", "salience": 0.9})
    record = next(iter(archive))
    assert record["id"] == record_id
    assert record["weight"] == "normal"
    assert record["tier_metadata"]["memory_tier"] == "high"


def test_l0_still_rejects_unknown_coarse_weight(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown weight"):
        L0Archive(tmp_path / "l0.jsonl").append("x", "event", weight="high")
