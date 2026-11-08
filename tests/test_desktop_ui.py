from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime
from cether.providers import ExpressionDirective, TurnResponse


def test_bootstrap_exposes_status_and_role_cards(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    payload = runtime.handle({"action": "bootstrap"})
    assert payload["active_role"]["name"] == "默认角色"
    assert payload["roles"][0]["active"] is True
    assert payload["view"]["status"]["sleep_status"] == "清醒"
    assert payload["view"]["status"]["mind_box"] == []
    runtime.handle({"action": "shutdown"})


def test_ui_actions_pause_capture_and_remember_are_visible(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    paused = runtime.handle({"action": "ui_action", "ui_action": "pause_capture", "payload": {"paused": True}})
    assert paused["accepted"] is True
    assert paused["payload"]["paused"] is True
    blocked = runtime.handle({"action": "ui_action", "ui_action": "look_now", "payload": {}})
    assert blocked["accepted"] is False
    assert blocked["feedback"]["status"] == "blocked"
    remembered = runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "用户喜欢夜空"}})
    assert remembered["accepted"] is True
    records = [json.loads(line) for line in (runtime.registry.active.workspace / "memory" / "l0.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["tier_metadata"]["memory_tier"] == "high"
    runtime.handle({"action": "shutdown"})


def test_memory_timeline_returns_role_local_records(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "role local memory"}})
    page = runtime.handle({"action": "memory_timeline", "limit": 10})
    assert page["total"] == 1
    assert page["records"][0]["text"] == "role local memory"
    with pytest.raises(ValueError):
        runtime.handle({"action": "memory_timeline", "limit": 0})
    runtime.handle({"action": "shutdown"})


def test_send_message_surfaces_backend_retrieval_degradation_without_blocking_reply(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.conversation._l0.append("后台失效候选记忆", "acceptance")
    fail = lambda _items: (_ for _ in ()).throw(RuntimeError("backend slots offline"))
    runtime.conversation.retrieval.embedding_provider = fail
    runtime.conversation.retrieval.graph_provider = None
    runtime.conversation.retrieval.spatial_provider = None
    response = runtime.handle({"action": "send_message", "text": "后台失效候选记忆"})
    assert response["turn"]["role"] == "assistant"
    assert response["turn"]["text"].strip()
    assert response["retrieval"] == {
        "degraded": True,
        "channel": "none",
        "error": "RuntimeError: backend slots offline",
        "result_count": 0,
        "budget_exceeded": False,
    }
    assert [row["role"] for row in response["history"]][-2:] == ["user", "assistant"]
    state = json.loads((runtime.registry.active.workspace / "state.json").read_text(encoding="utf-8"))
    assert state["dimensions"]["social_battery"] < 0.8
    runtime.handle({"action": "shutdown"})


def test_desktop_response_exposes_corpus_structured_expression_to_ui(tmp_path: Path) -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "expression.structured.precedence")
    runtime = DesktopRuntime(tmp_path)
    runtime.conversation.provider.respond = lambda _request: TurnResponse(
        case["input"]["text"], emotion=case["input"]["emotion"],
        directive=ExpressionDirective(**case["input"]["directive"]),
    )

    result = runtime.handle({"action": "send_message", "text": "选择结构化表达"})

    assert result["turn"]["directive"] == case["input"]["directive"]
    assert result["turn"]["resolved_expression"]["emotion"] == "joyful"
    assert result["turn"]["resolved_expression"]["expression"] == "smile"
    assert result["turn"]["resolved_expression"]["action"] == "nod"
    assert result["history"][-1]["resolved_expression"] == result["turn"]["resolved_expression"]
    assert case["expected"]["directive_precedes_inference"] is True
    runtime.handle({"action": "shutdown"})


def test_onboarding_local_fallback_and_expression_presentation_are_persistent(tmp_path: Path) -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    onboarding_case = next(case for case in corpus["cases"] if case["id"] == "onboarding.local_fallback")
    expression_case = next(case for case in corpus["cases"] if case["id"] == "expression.presentation.preference")
    runtime = DesktopRuntime(tmp_path)
    initial = runtime.handle({"action": "bootstrap"})
    assert initial["onboarding"]["completed"] is False
    assert initial["onboarding"]["modules"] == onboarding_case["input"]["modules"]
    completed = runtime.handle({"action": "complete_onboarding", "local_fallback": True})
    assert completed["onboarding"]["completed"] is onboarding_case["expected"]["completed_persisted"]
    assert completed["onboarding"]["local_fallback"] is True
    assert runtime.conversation.provider.__class__.__name__ == "LocalRuleProvider"
    preference = runtime.handle({"action": "set_expression_presentation", "mode": expression_case["input"]["mode"]})
    assert preference["mode"] == "silent"
    assert runtime.handle({"action": "bootstrap"})["expression_presentation"] == "silent"
    with pytest.raises(ValueError, match="popup or silent"):
        runtime.handle({"action": "set_expression_presentation", "mode": "interrupt"})
    runtime.handle({"action": "shutdown"})


def test_role_switch_returns_progress_and_rebinds_ui(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    first = runtime.handle({"action": "bootstrap"})
    created = runtime.handle({"action": "create_role", "name": "工作角色"})
    switched = runtime.handle({"action": "switch_role", "role_id": first["active_role"]["role_id"]})
    assert switched["active_role"]["role_id"] == first["active_role"]["role_id"]
    assert len(switched["switch_progress"]) == 6
    assert switched["wake_pending"] is True
    assert created["active_role"]["name"] == "工作角色"
    runtime.handle({"action": "shutdown"})


def test_manual_mode_override_is_visible_and_clearable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = DesktopRuntime(tmp_path)
    monkeypatch.setattr(runtime, "_foreground_app", lambda: "code")
    automatic = runtime.handle({"action": "bootstrap"})["view"]["status"]
    assert (automatic["mode"], automatic["mode_source"]) == ("work", "automatic")

    overridden = runtime.handle({"action": "set_mode", "mode": "companion"})
    assert overridden == {"mode": "companion", "source": "manual", "override": "companion"}
    status = runtime.handle({"action": "bootstrap"})["view"]["status"]
    assert (status["mode"], status["mode_source"]) == ("companion", "manual")

    cleared = runtime.handle({"action": "set_mode", "mode": None})
    assert cleared == {"mode": "work", "source": "automatic", "override": None}
    runtime.handle({"action": "shutdown"})
