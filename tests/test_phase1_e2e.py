from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime
from cether.providers import TurnResponse


class CaptureProvider:
    def __init__(self) -> None:
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return TurnResponse("已记录这件重要的关系事件。", kind="full", emotion="warm")


def test_high_event_reaches_spatial_retrieval_and_conversation_context(tmp_path: Path) -> None:
    desktop = DesktopRuntime(tmp_path)
    capture = CaptureProvider()
    desktop.conversation.provider = capture
    runtime = desktop.runtime
    runtime.event_metadata = lambda event: {
        "source": "perception",
        "manual_mark": True,
        "emotion_intensity": 0.95,
        "salience": 0.95,
        "is_relation_event": True,
    }
    runtime.perception_provider = lambda: {"description": "important relation event", "changed": True}
    pipeline = runtime.build_pipeline()
    context = pipeline.tick()
    record = next(item for item in runtime._l0 if item.get("text") == "important relation event")
    assert record["tier_metadata"]["memory_tier"] == "high"

    result = desktop.handle({"action": "send_message", "text": "important relation"})
    assert capture.requests[-1].recent_memories == ("important relation event",)
    assert runtime._pipeline is not None
    assert runtime._pipeline.role_scope == runtime.role.scope_id
    assert result["turn"]["text"] == "已记录这件重要的关系事件。"
    desktop.handle({"action": "shutdown"})


def test_deep_sleep_e2e_writes_traceable_products_and_bias(tmp_path: Path) -> None:
    desktop = DesktopRuntime(tmp_path)
    runtime = desktop.runtime
    service = runtime.sleep_provider.__self__
    for text in ("low dream one", "low dream two", "low dream three"):
        service.l0.append(text, "silent", "low")
    service.l0.append("normal project note", "perception", "normal")
    runtime.sleep_mode_provider = lambda _role, _now: "deep"
    context = runtime.build_pipeline().tick()
    assert context.background_results["sleep_consolidation"]["mode"] == "light"
    assert context.background_results["reflection_calibration"]["source_l0_ids"]
    assert context.background_results["retrieval_bias_update"]["indexed_candidates"] >= 1
    records = [json.loads(line) for line in (runtime.role.workspace / "memory" / "l1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {item["emotion_tag"] for item in records} == {"dream", "reflection"}
    assert all(item["source_l0_ids"] for item in records)
    assert (runtime.role.workspace / "retrieval_bias.json").is_file()
    desktop.handle({"action": "shutdown"})
