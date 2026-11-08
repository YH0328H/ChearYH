from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime
from cether.events import RuntimeEvents
from cether.state import (
    FourWill,
    SixDrives,
    detect_tension_state,
    inertial_filter,
    project_six_drives_to_four_will,
)
from cether.presets import register_presets


def test_acceptance_corpus_is_versioned_and_actionable() -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    assert corpus["format"] == "cetheryh-acceptance-corpus"
    cases = corpus["cases"]
    assert len(cases) >= 16
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case.get("area") and isinstance(case.get("input"), dict) and isinstance(case.get("expected"), dict)
               for case in cases)


def test_corpus_executable_event_and_config_cases(tmp_path: Path) -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in corpus["cases"]}
    event_case = cases["runtime.events.subscribe"]
    events = RuntimeEvents(tmp_path / "events.jsonl")
    events.record(event_case["input"]["new_event"], "acceptance corpus")
    batch = events.subscribe(event_case["input"]["cursor"])
    assert batch["events"][-1]["kind"] == event_case["input"]["new_event"]
    assert batch["cursor"] > event_case["input"]["cursor"]
    runtime = DesktopRuntime(tmp_path / "desktop")
    config_case = cases["config.retrieval.write"]
    current = runtime.handle({"action": "config_read", "name": "retrieval.toml"})
    current["values"]["retrieval"].update(config_case["input"])
    saved = runtime.handle({"action": "config_write", "name": "retrieval.toml", "values": current["values"]})
    assert saved["values"]["retrieval"]["top_k"] == config_case["input"]["top_k"]
    assert runtime.conversation.retrieval.config.get().latency_budget_ms == config_case["input"]["latency_budget_ms"]
    runtime.handle({"action": "shutdown"})


def test_acceptance_mapping_covers_all_task_ids_and_existing_evidence() -> None:
    import re

    mapping = (ROOT / "ACCEPTANCE_MAPPING.md").read_text(encoding="utf-8")
    ids = {int(match) for match in re.findall(r"^\|\s*(\d+)\s*\|", mapping, flags=re.MULTILINE)}
    assert ids == set(range(1, 64))
    evidence = set(re.findall(r"`((?:tests|src/cether|benchmarks)/[^`]+)`", mapping))
    missing = sorted(path for path in evidence if not (ROOT / path).is_file())
    assert missing == []


def test_backend_retrieval_failures_degrade_without_memory_hits(tmp_path: Path) -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in corpus["cases"]}
    runtime = DesktopRuntime(tmp_path)
    scenarios = (
        ("retrieval.embedding.failure", "embedding", "normal"),
        ("retrieval.graph.failure", "graph", "normal"),
        ("retrieval.vector.failure", "vector", "normal"),
        ("retrieval.spatial.failure", "spatial", "high"),
    )
    for case_id, channel, tier in scenarios:
        case = cases[case_id]
        memory = case["input"]["memory"]
        metadata = {"memory_tier": "high", "salience": 1.0} if tier == "high" else None
        runtime.conversation._l0.append(memory, "acceptance", metadata=metadata)
        provider_error = case["input"]["provider_error"]

        def fail(_items, error=provider_error):
            raise RuntimeError(error)

        retrieval = runtime.conversation.retrieval
        retrieval.embedding_provider = (
            fail if channel == "embedding"
            else (lambda texts: [[1.0, 0.0] for _ in texts]) if channel == "vector"
            else None
        )
        retrieval.graph_provider = fail if channel == "graph" else None
        retrieval.spatial_provider = (lambda _query, _records, error=provider_error: fail([], error)) if channel == "spatial" else None
        state_before = runtime.runtime._read_state()["social_battery"]
        l0_path = runtime.conversation._l0.path
        l0_before = len(l0_path.read_text(encoding="utf-8").splitlines())

        from contextlib import nullcontext
        from unittest.mock import patch
        vector_failure = patch("cether.memory_retrieval.VectorRetrieval.search", side_effect=RuntimeError(provider_error)) if channel == "vector" else nullcontext()
        with vector_failure:
            result = runtime.handle({"action": "send_message", "text": case["input"]["query"]})
        assert result["turn"]["role"] == "assistant"
        assert result["turn"]["text"].strip()
        assert result["retrieval"]["degraded"] is True
        assert result["retrieval"]["channel"] == "none"
        assert result["retrieval"]["result_count"] == 0
        assert case["expected"]["memories_injected"] is False
        assert case["expected"]["state_evolves"] is True
        assert result["retrieval"]["error"].endswith(provider_error)
        assert [row["role"] for row in result["history"]][-2:] == ["user", "assistant"]
        state_after = runtime.runtime._read_state()["social_battery"]
        assert state_after < state_before
        l0_after = l0_path.read_text(encoding="utf-8").splitlines()
        assert len(l0_after) == l0_before + 2
        appended = [json.loads(line) for line in l0_after[-2:]]
        assert [record["text"] for record in appended] == [case["input"]["query"], result["turn"]["text"]]
    runtime.handle({"action": "shutdown"})


def test_tool_result_is_role_scoped_and_artifact_stays_out_of_memory(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    first = runtime.registry.active
    first_result = runtime.handle({
        "action": "tool_notice", "kind": "report_ready", "description": "done",
        "artifact_name": "report.txt", "artifact_content": "role-one output",
    })
    assert first_result["role_id"] == first.config.role_id
    assert first_result["artifact"] == "artifacts/tools/report.txt"
    first_artifact = first.workspace / first_result["artifact"]
    assert first_artifact.read_text(encoding="utf-8") == "role-one output"
    assert first_result["memory_written"] is False
    assert not (first.workspace / "memory" / "l0.jsonl").exists()

    second = runtime.registry.create_role("Tool Result Role", tmp_path / "tool-result-role")
    runtime.handle({"action": "switch_role", "role_id": second.role_id})
    second_result = runtime.handle({
        "action": "tool_notice", "kind": "report_ready", "description": "done",
        "artifact_name": "report.txt", "artifact_content": "role-two output",
    })
    assert second_result["role_id"] == second.role_id
    assert (second.workspace / second_result["artifact"]).read_text(encoding="utf-8") == "role-two output"
    assert first_artifact.read_text(encoding="utf-8") == "role-one output"
    assert not (second.workspace / "memory" / "l0.jsonl").exists()
    second_events = runtime.handle({"action": "runtime_events", "cursor": 0})["events"]
    assert second_events[-1]["metadata"]["role_id"] == second.role_id
    assert second_events[-1]["metadata"]["memory_written"] is False
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "tools.failure.world_notice")
    world_log = second.workspace / "world.jsonl"
    for status in ("failure", "timeout"):
        failed = runtime.handle({"action": "tool_notice", **case["input"], "status": status})
        assert failed["visible"] is case["expected"]["visible_notice"]
        assert failed["status"] == status
        assert failed["role_id"] == second.role_id
        assert failed["memory_written"] is case["expected"]["memory_written"]
        assert world_log.is_file() is case["expected"]["role_world_log"]
        events = runtime.handle({"action": "runtime_events", "cursor": 0})["events"]
        failed_event = events[-1]
        assert failed_event["kind"] == f"tool_{status}"
        assert failed_event["description"] == case["input"]["description"]
        assert failed_event["metadata"]["role_id"] == second.role_id
        assert failed_event["metadata"]["memory_written"] is False
        assert case["expected"]["event_subscribable"] is True
        world_record = json.loads(world_log.read_text(encoding="utf-8").splitlines()[-1])
        assert {key: value for key, value in world_record.items() if key != "ts"} == {
            key: value for key, value in failed_event.items() if key != "ts"
        }
    html = (ROOT / "dist" / "index.html").read_text(encoding="utf-8")
    assert "showStatus(`${event.kind}: ${event.description}`)" in html
    assert not (second.workspace / "memory" / "l0.jsonl").exists()

    with pytest.raises(ValueError, match="plain filename"):
        runtime.handle({"action": "tool_notice", "artifact_name": "../escape.txt", "artifact_content": "x"})
    runtime.handle({"action": "shutdown"})


def test_skill_registry_defaults_off_and_is_shared_across_roles(tmp_path: Path) -> None:
    from cether.skills import ToolDeclaration

    runtime = DesktopRuntime(tmp_path)
    case = next(
        item for item in json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))["cases"]
        if item["id"] == "skill.registry.default_disabled"
    )
    spec = case["input"]
    expected = case["expected"]

    assert runtime.handle({"action": "bootstrap"})["skills"]["tools"] == []
    assert expected["default_disabled"] is True
    declaration = ToolDeclaration(
        spec["tool_name"], spec["parameter_schema"], spec["return_type"],
        asynchronous=spec["asynchronous"], low_frequency=spec["low_frequency"],
    )
    installed = runtime.skills.install(spec["skill_id"], declaration, lambda args: {"matches": [args["query"]]})
    assert installed is None
    installed_state = runtime.handle({"action": "skills_list"})
    assert installed_state["tools"] == []
    assert installed_state["skills"][0] == {
        "id": spec["skill_id"], "installed": True, "enabled": False, "tools": [],
    }
    with pytest.raises(KeyError, match="not enabled"):
        runtime.handle({"action": "tool_invoke", "name": spec["tool_name"], "arguments": {"query": spec["query"]}})
    assert expected["disabled_rejects_invocation"] is True

    enabled = runtime.handle({"action": "skill_enable", "skill_id": spec["skill_id"], "enabled": True})
    assert enabled["tools"] == [{
        "name": spec["tool_name"], "parameters": spec["parameter_schema"], "returns": spec["return_type"],
        "asynchronous": spec["asynchronous"], "low_frequency": spec["low_frequency"],
    }]
    assert enabled["skills"][0]["installed"] is True
    assert enabled["skills"][0]["enabled"] is True
    assert runtime.handle({"action": "tool_invoke", "name": spec["tool_name"],
                           "arguments": {"query": spec["query"]}}) == {"result": {"matches": [spec["query"]]}}
    with pytest.raises(ValueError, match="do not match"):
        runtime.handle({"action": "tool_invoke", "name": spec["tool_name"], "arguments": {}})
    with pytest.raises(ValueError, match="invalid type"):
        runtime.handle({"action": "tool_invoke", "name": spec["tool_name"], "arguments": {"query": 4}})
    assert expected["registered_only_when_enabled"] is True
    assert expected["schema_rejected"] is True

    created = runtime.handle({"action": "create_role", "name": "Second Role"})
    assert created["skills"]["tools"] == enabled["tools"]
    assert created["skills"]["skills"][0]["enabled"] is True
    disabled = runtime.handle({"action": "skill_enable", "skill_id": spec["skill_id"], "enabled": False})
    assert disabled["tools"] == []
    assert expected["global_shared"] is True
    with pytest.raises(KeyError, match="not enabled"):
        runtime.handle({"action": "tool_invoke", "name": spec["tool_name"], "arguments": {"query": spec["query"]}})
    runtime.handle({"action": "shutdown"})


def test_continuous_event_subscription_advances_cursor(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    events = runtime.handle({"action": "runtime_events", "cursor": 0})
    runtime.handle({"action": "tool_notice", "kind": "acceptance", "description": "fresh event"})
    batch = runtime.handle({"action": "runtime_events", "cursor": events["cursor"]})
    assert batch["events"][-1]["description"] == "fresh event"
    assert batch["cursor"] > events["cursor"]
    first_role = batch["role_id"]
    other = runtime.registry.create_role("Event Role", tmp_path / "event-role")
    switched = runtime.handle({"action": "switch_role", "role_id": other.role_id})
    assert switched["active_role"]["role_id"] == other.role_id
    role_batch = runtime.handle({"action": "runtime_events", "cursor": 0})
    assert role_batch["role_id"] != first_role
    assert role_batch["events"] == []
    runtime.handle({"action": "shutdown"})


def test_config_write_roundtrip_and_path_validation(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    current = runtime.handle({"action": "config_read", "name": "retrieval.toml"})
    current["values"]["retrieval"]["top_k"] = 17
    saved = runtime.handle({"action": "config_write", "name": "retrieval.toml", "values": current["values"]})
    assert saved["values"]["retrieval"]["top_k"] == 17
    cognition = runtime.handle({"action": "config_read", "name": "cognition.toml"})
    cognition["values"]["decision"]["default_priority"] = 0.65
    saved_cognition = runtime.handle({"action": "config_write", "name": "cognition.toml", "values": cognition["values"]})
    assert saved_cognition["values"]["decision"]["default_priority"] == 0.65
    with pytest.raises(ValueError):
        runtime.handle({"action": "config_read", "name": "../secrets.toml"})
    with pytest.raises(ValueError, match="not editable"):
        runtime.handle({"action": "config_write", "name": "window.toml", "values": {"checkpoint": {}}})
    altered = runtime.handle({"action": "config_read", "name": "retrieval.toml"})["values"]
    altered["retrieval"]["unknown_parameter"] = 1
    with pytest.raises(ValueError, match="keys must match"):
        runtime.handle({"action": "config_write", "name": "retrieval.toml", "values": altered})
    runtime.handle({"action": "shutdown"})


def test_role_package_contains_required_role_card_files_and_excludes_global_config(tmp_path: Path) -> None:
    from cether.roles import RoleRegistry

    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "role.package.complete")
    registry = RoleRegistry(tmp_path / "registry.json")
    role = registry.create_role(case["input"]["name"], tmp_path / "source")
    expected_files = case["input"]["role_card_files"]
    values = {
        "persona.md": "Persona fixture",
        "boundaries.md": "Boundary fixture",
        "appearance.json": '{"avatar":"fixture.png"}',
        "expression.json": '{"happy":"smile"}',
        "window.toml": "[[window]]\nname='work'\nstart='09:00'\nend='17:00'\n",
        "checkpoint.toml": "[checkpoint]\ninterval_seconds=900\n",
    }
    for filename in expected_files:
        (role.workspace / filename).write_text(values[filename], encoding="utf-8")
    state = '{"social_battery":0.37,"connection_desire":0.81}'
    mind_box = '[{"text":"unfinished thought"}]'
    memory = '{"id":"memory-1","text":"remembered fixture"}\n'
    (role.workspace / "state.json").write_text(state, encoding="utf-8")
    (role.workspace / "mind_box.json").write_text(mind_box, encoding="utf-8")
    (role.workspace / "memory" / "l0.jsonl").parent.mkdir(parents=True, exist_ok=True)
    source_memory = role.workspace / "memory" / "l0.jsonl"
    source_memory.write_text(memory, encoding="utf-8")
    expected_memory_bytes = source_memory.read_bytes()
    (role.workspace / "chat.toml").write_text("[provider]\nmodel='global'\n", encoding="utf-8")
    package = registry.export_package(role.role_id, tmp_path / "role.zip")
    with zipfile.ZipFile(package) as archive:
        members = set(archive.namelist())
        packaged_memory = archive.read("memory/l0.jsonl").decode("utf-8")
    assert set(expected_files).issubset(members)
    assert {"state.json", "mind_box.json", "memory/l0.jsonl"}.issubset(members)
    assert "chat.toml" not in members
    assert "embedding.toml" not in members
    manifest = json.loads(zipfile.ZipFile(package).read("package.json"))
    assert manifest["wake_on_import"] is case["expected"]["wake_on_import"]
    assert set(expected_files).issubset(manifest["included"])
    assert "memory/" in manifest["included"]
    assert "global_channels" in manifest["excluded"]

    target = tmp_path / "imported"
    imported = registry.import_package(package, target, conflict="rename", renamed_to="Imported Fixture")
    for filename, expected in values.items():
        assert (imported.workspace / filename).read_text(encoding="utf-8") == expected
    assert (imported.workspace / "state.json").read_text(encoding="utf-8") == state
    assert (imported.workspace / "mind_box.json").read_text(encoding="utf-8") == mind_box
    assert (imported.workspace / "memory" / "l0.jsonl").read_bytes() == expected_memory_bytes
    assert packaged_memory.encode("utf-8") == expected_memory_bytes
    assert (imported.workspace / "wake.json").exists()
    pending_wake = registry.pending_wake(imported.role_id)
    assert pending_wake is not None
    assert pending_wake.snapshot["imported_from"] == str(package)
    assert not (imported.workspace / "chat.toml").exists()


def test_imported_role_wake_is_consumed_by_first_desktop_conversation(tmp_path: Path) -> None:
    from cether.providers import TurnResponse
    from cether.wake import render_injection

    runtime = DesktopRuntime(tmp_path / "desktop")
    package_case = next(
        item for item in json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))["cases"]
        if item["id"] == "role.package.complete"
    )
    source = runtime.registry.create_role(package_case["input"]["name"], tmp_path / "source")
    (source.workspace / "persona.md").write_text("Package persona", encoding="utf-8")
    package = runtime.registry.export_package(source.role_id, tmp_path / "imported.cether-role")
    imported = runtime.handle({
        "action": "role_import",
        "package": str(package),
        "workspace": str(tmp_path / "imported"),
        "conflict": "rename",
        "renamed_to": "Imported Wake Fixture",
    })
    assert imported["wake_pending"] is True
    runtime.handle({"action": "switch_role", "role_id": imported["role_id"]})
    pending_before = runtime.registry.pending_wake(imported["role_id"])
    assert pending_before is not None

    class WakeCaptureProvider:
        request = None

        def respond(self, request):
            self.request = request
            return TurnResponse("First imported-role reply")

    provider = WakeCaptureProvider()
    runtime.conversation.provider = provider
    result = runtime.handle({"action": "send_message", "text": "Continue from the imported role"})
    assert result["turn"]["text"] == "First imported-role reply"
    assert provider.request.wake_context == render_injection(pending_before)
    assert str(package) in provider.request.wake_context
    assert runtime.registry.pending_wake(imported["role_id"]) is None
    assert len(result["history"]) == 2
    runtime.handle({"action": "shutdown"})


def test_starfield_returns_render_nodes_edges_and_lifecycle_metadata(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "acceptance star night"}})
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "acceptance star sky"}})
    result = runtime.handle({"action": "memory_starfield"})
    assert result["view"] == "galaxy"
    assert result["total"] >= 2
    assert 0 <= result["nodes"][0]["x"] <= 1
    assert result["edges"]
    assert all(node["lifecycle_status"] == "hot" for node in result["nodes"])
    runtime.handle({"action": "shutdown"})


def test_star_map_actions_persist_deepen_and_leave_l0_immutable(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "deepen acceptance memory"}})
    memory_id = next(iter(runtime._lifecycle.archive))["id"]
    raw_before = runtime._lifecycle.archive.path.read_bytes()
    result = runtime.handle({"action": "ui_action", "ui_action": "deepen", "payload": {"memory_id": memory_id}})
    assert result["accepted"]
    assert result["payload"]["weight"] > 0.5
    assert runtime._lifecycle.annotate(runtime._lifecycle._record(memory_id))["lifecycle_weight_factor"] > 1
    assert runtime._lifecycle.archive.path.read_bytes() == raw_before
    thought = runtime.handle({"action": "ui_action", "ui_action": "think_again", "payload": {"memory_id": memory_id}})
    assert thought["feedback"]["status"] == "completed"
    runtime.handle({"action": "shutdown"})


def test_create_role_from_preset_materializes_persona_and_runtime_metadata(tmp_path: Path) -> None:
    runtime = DesktopRuntime(tmp_path)
    presets = runtime.handle({"action": "preset_list"})
    assert {item["id"] for item in presets} >= {"companion", "work"}
    created = runtime.handle({"action": "create_role", "name": "Preset Work", "preset_id": "work"})
    role = runtime.registry.active.config
    workspace = role.workspace
    assert "直接、严谨" in (workspace / "persona.md").read_text(encoding="utf-8")
    assert json.loads((workspace / "role-preset.json").read_text(encoding="utf-8"))["mode"] == "work"
    runtime.handle({"action": "shutdown"})


def test_preset_upgrade_preserves_user_modified_copy(tmp_path: Path) -> None:
    bundled = ROOT / "presets"
    assert {"companion.yaml", "work.yaml"}.issubset({path.name for path in bundled.glob("*.yaml")})
    source, dest = tmp_path / "bundle", tmp_path / "user"
    source.mkdir()
    (source / "agent.yaml").write_text("version: 1\nprompt: base\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    first = register_presets(source, dest, manifest)
    assert first[0].status == "registered"
    (source / "agent.yaml").write_text("version: 2\nprompt: upgraded\n", encoding="utf-8")
    assert register_presets(source, dest, manifest)[0].status == "upgraded"
    (dest / "agent.yaml").write_text("version: 2\nprompt: user customization\n", encoding="utf-8")
    (source / "agent.yaml").write_text("version: 3\nprompt: v3\n", encoding="utf-8")
    assert register_presets(source, dest, manifest)[0].status == "user_copy"
    assert "user customization" in (dest / "agent.yaml").read_text(encoding="utf-8")


def test_manual_mode_override_is_detectable_visible_and_clearable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = json.loads((ROOT / "acceptance" / "corpus.json").read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == "ui.mode.override")
    runtime = DesktopRuntime(tmp_path)
    monkeypatch.setattr(runtime, "_foreground_app", lambda: case["input"]["automatic_app"])

    automatic = runtime.handle({"action": "bootstrap"})["view"]["status"]
    assert automatic["mode"] == "work"
    assert automatic["mode_source"] == "automatic"

    changed = runtime.handle({"action": "set_mode", "mode": case["input"]["manual_mode"]})
    assert changed["mode"] == case["input"]["manual_mode"]
    assert changed["source"] == "manual"
    view = runtime.handle({"action": "bootstrap"})["view"]["status"]
    assert view["mode"] == case["input"]["manual_mode"]
    assert view["mode_source"] == "manual"

    cleared = runtime.handle({"action": "set_mode", "mode": None})
    assert cleared["mode"] == "work"
    assert cleared["source"] == "automatic"
    runtime.handle({"action": "shutdown"})


def test_tension_derivations_match_runtime_projection_and_detection() -> None:
    report = json.loads((ROOT / "acceptance" / "tension_derivations.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    alpha = report["alpha"]
    for case in report["scenarios"]:
        current = SixDrives(**case["current_drives"])
        target = SixDrives(**case["target_drives"])
        filtered_values = {
            field: inertial_filter(getattr(current, field), getattr(target, field), alpha)
            for field in current.__dataclass_fields__
        }
        assert filtered_values == pytest.approx(case["filtered_drives"])
        filtered = SixDrives(**filtered_values)
        battery = inertial_filter(case["current_social_battery"], case["target_social_battery"], alpha)
        will = project_six_drives_to_four_will(filtered, battery)
        actual_will = {field: getattr(will, field) for field in will.__dataclass_fields__}
        assert actual_will == pytest.approx(case["expected_will"])
        hits = detect_tension_state(will, report["relation_tension"], report["momentary_valence"])
        actual_names = [hit.name for hit in hits]
        assert actual_names == case["expected_tension_states"]
        evidence_by_name = {hit.name: hit.evidence for hit in hits}
        assert evidence_by_name[case["name"]] == pytest.approx({
            key: actual_will[key] for key in case["expected_will"]
            if key in evidence_by_name[case["name"]]
        } | {"relation_tension": report["relation_tension"]})


def test_event_subscription_rejects_invalid_cursor_and_limit(tmp_path: Path) -> None:
    events = RuntimeEvents(tmp_path / "events.jsonl")
    with pytest.raises(ValueError):
        events.subscribe(-1)
    with pytest.raises(ValueError):
        events.subscribe(0, 501)
