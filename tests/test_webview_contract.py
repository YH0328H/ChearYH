from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops
import pytest
from playwright.sync_api import Page, expect

ROOT = Path(__file__).resolve().parents[1]
VISUAL_BASELINES = ROOT / "tests" / "visual_baselines"
VISUAL_DIFF_LIMIT = 0.015
sys.path.insert(0, str(ROOT / "src"))


def assert_visual_baseline(page: Page, name: str, actual_path: Path, selector: str | None = None) -> None:
    baseline = VISUAL_BASELINES / f"{name}.png"
    capture = page.locator(selector) if selector else page
    if os.environ.get("UPDATE_VISUAL_BASELINES") == "1":
        baseline.parent.mkdir(parents=True, exist_ok=True)
        capture.screenshot(path=str(baseline)) if selector else capture.screenshot(path=str(baseline), full_page=True)
        return
    if not baseline.exists():
        pytest.fail(f"missing visual baseline: {baseline}")
    capture.screenshot(path=str(actual_path)) if selector else capture.screenshot(path=str(actual_path), full_page=True)
    with Image.open(baseline).convert("RGBA") as expected, Image.open(actual_path).convert("RGBA") as actual:
        assert actual.size == expected.size, f"{name}: screenshot dimensions changed: {actual.size} != {expected.size}"
        changed = ImageChops.difference(expected, actual)
        changed_pixels = sum(1 for pixel in changed.get_flattened_data() if pixel[:3] != (0, 0, 0))
        ratio = changed_pixels / (actual.width * actual.height)
        assert ratio <= VISUAL_DIFF_LIMIT, f"{name}: changed pixel ratio {ratio:.3%} > {VISUAL_DIFF_LIMIT:.1%}"


class RuntimeHandler(SimpleHTTPRequestHandler):
    runtime = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/__events":
            batch = self.runtime.handle({"action": "runtime_events", "cursor": int(self.headers.get("X-Cursor", "0"))})
            events = batch["events"]
            body = json.dumps({"events": events, "cursor": batch["cursor"]}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/__runtime":
            self.send_error(404)
            return
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            command = payload["command"]
            args = payload.get("args") or {}
            actions = {
                "app_bootstrap": ("bootstrap", {}),
                "complete_onboarding": ("complete_onboarding", {"payload": {"local_fallback": args.get("local_fallback", False)}}),
                "set_expression_presentation": ("set_expression_presentation", {"payload": {"mode": args.get("mode", "popup")}}),
                "send_message": ("send_message", args),
                "config_read": ("config_read", args),
                "config_write": ("config_write", args),
                "memory_timeline": ("memory_timeline", args),
                "memory_starfield": ("memory_starfield", args),
                "preset_list": ("preset_list", args),
                "create_role": ("create_role", {"name": args.get("name", ""), "preset_id": args.get("presetId", "")}),
                "role_import": ("role_import", {"package_base64": args.get("package_base64"), "workspace": args.get("workspace"), "conflict": args.get("conflict", "rename"), "renamed_to": args.get("renamed_to")}),
                "switch_role": ("switch_role", {"role_id": args.get("roleId", "")}),
                "ui_action": ("ui_action", {"ui_action": args.get("action"), "payload": args.get("payload", {})}),
                "runtime_action": (args.get("action"), args.get("payload", {})),
                "runtime_events_ready": ("runtime_events", {"cursor": args.get("cursor", 0)}),
            }
            action, body_args = actions[command]
            result = self.runtime.handle({"action": action, **body_args})
            body = json.dumps({"result": result}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
        except Exception as exc:  # the browser should receive the same IPC failure shape
            body = json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args) -> None:
        pass


@pytest.fixture

def ui_page(tmp_path: Path):
    from cether.desktop import DesktopRuntime
    from playwright.sync_api import sync_playwright

    from cether.skills import ToolDeclaration

    runtime = DesktopRuntime(tmp_path / "runtime")
    runtime.skills.install("fixture.lookup", ToolDeclaration("lookup", {"type": "object", "properties": {}}, "string"), lambda _args: "ok")
    RuntimeHandler.runtime = runtime
    server = ThreadingHTTPServer(("127.0.0.1", 18000), RuntimeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        context.add_init_script(f"""window.__cetherListeners = {{}};
        window.__TAURI__ = {{ event: {{ listen: async (name, callback) => {{
          (window.__cetherListeners[name] ||= []).push(callback); return () => {{}};
        }} }}, core: {{ invoke: async (command, args={{}}) => {{
          if (command === 'runtime_events_ready') {{ let cursor=args.cursor||0; window.__cetherEventPoll=setInterval(async()=>{{const response=await fetch('http://127.0.0.1:{server.server_port}/__events',{{headers:{{'X-Cursor':String(cursor)}}}});const batch=await response.json();if(batch.events.length){{cursor=batch.cursor;(window.__cetherListeners['cether://runtime-events']||[]).forEach(fn=>fn({{payload:batch.events}}))}}}},40); return {{ready:true}}; }}
          const response = await fetch('http://127.0.0.1:{server.server_port}/__runtime', {{
            method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{command,args}})
          }});
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error);
          return payload.result;
        }} }} }};""")
        page = context.new_page()
        try:
            page.goto(f"http://127.0.0.1:{server.server_port}/dist/index.html", wait_until="domcontentloaded")
            expect(page.locator("#roleName")).to_have_text("默认角色")
            expect(page.locator("#onboarding")).to_be_visible()
            expect(page.locator("#onboardingModules li")).to_have_count(6)
            page.locator("#finishOnboarding").click()
            expect(page.locator("#onboarding")).not_to_be_visible()
            yield page, runtime
        finally:
            context.close()
            browser.close()
            runtime.handle({"action": "shutdown"})
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            RuntimeHandler.runtime = None


def open_view(page: Page, view: str) -> None:
    page.locator("#menu").click()
    page.locator(f"#drawer [data-view={view}]").click()


def test_expression_presentation_preference_persists_and_selects_silent(ui_page):
    page, runtime = ui_page
    open_view(page, "settings")
    page.locator('[name="expressionPresentation"][value="silent"]').check()
    expect(page.locator("#statusLine")).to_contain_text("静默")
    assert runtime.handle({"action": "bootstrap"})["expression_presentation"] == "silent"
    page.reload()
    expect(page.locator('[name="expressionPresentation"][value="silent"]')).to_be_checked()


def test_desktop_runtime_bootstrap_and_chat_render(ui_page):
    page, _runtime = ui_page
    page.locator("#input").fill("playwright conversation")
    page.locator("#send").click()
    expect(page.locator(".message.assistant .bubble")).to_contain_text("playwright conversation", timeout=10_000)


def test_star_map_five_views_render_nonblank(ui_page, tmp_path: Path):
    page, runtime = ui_page
    runtime.handle({"action": "ui_action", "ui_action": "remember_this", "payload": {"text": "星图验收记忆"}})
    open_view(page, "memories")
    for view in ("galaxy", "nebula", "clusters", "timeline", "list"):
        page.locator(f"[data-map-view={view}]").click()
        expect(page.locator("#memoryCount")).to_contain_text(view)
        expect(page.locator("#memoryCount")).to_contain_text("1 /")
        assert_visual_baseline(page, f"star-map-{view}", tmp_path / f"star-map-{view}.png", selector="#memories")
        if view in {"timeline", "list"}:
            expect(page.locator("#memoryList [data-memory-id]")).to_have_count(1)
        else:
            canvas = page.locator("#starfield")
            pixels = canvas.evaluate("el => { const c=el.getContext('2d'); return c.getImageData(0,0,el.width,el.height).data }")
            assert any(pixels[index] != 11 for index in range(0, len(pixels), 4))


def test_role_package_import_preset_and_skill_panel(ui_page, tmp_path: Path):
    page, runtime = ui_page
    source = runtime.registry.active
    package = runtime.registry.export_package(source.config.role_id, tmp_path / "source.cether-role")
    open_view(page, "rolesPanel")
    page.locator("#newRoleName").fill("Preset Companion")
    expect(page.locator("#rolePreset option")).to_have_count(2)
    page.locator("#createRoleButton").click()
    expect(page.locator("#roleName")).to_have_text("Preset Companion")
    expect(page.locator("#onboarding")).not_to_be_visible()
    expect(page.locator("#roleCreateFeedback")).to_contain_text("已创建")

    page.locator("#roleImportName").fill("Imported Companion")
    page.locator("#rolePackageFile").set_input_files(str(package))
    page.locator("#importRoleButton").click()
    expect(page.locator("#roleImportFeedback")).to_contain_text("Imported Companion")
    refreshed = runtime.handle({"action": "bootstrap"})
    assert any(role["name"] == "Imported Companion" for role in refreshed["roles"])

    toggle = page.get_by_label("启用技能 fixture.lookup")
    expect(toggle).not_to_be_checked()
    toggle.check()
    expect(page.locator("#skillFeedback")).to_have_text("技能已全局启用")
    assert runtime.handle({"action": "skills_list"})["skills"][0]["enabled"] is True
    assert_visual_baseline(page, "roles-panel", tmp_path / "roles-panel.png")


def test_tool_notice_event_is_delivered_to_ui(ui_page):
    page, runtime = ui_page
    page.wait_for_function("() => window.__cetherEventPoll !== undefined")
    runtime.handle({"action": "tool_notice", "kind": "tool", "status": "failure", "description": "search offline"})
    page.wait_for_function("() => document.querySelector('#statusLine').textContent.includes('search offline')", timeout=3000)
    assert page.locator("#statusLine").inner_text() == "tool_failure: search offline"


def test_config_write_persists_via_desktop_ipc(ui_page):
    page, runtime = ui_page
    open_view(page, "settings")
    field = page.locator("#configFields input[data-key=top_k]")
    field.fill("12")
    page.locator("#saveConfig").click()
    expect(page.locator("#configNotice")).to_contain_text("已保存")
    assert runtime.handle({"action": "config_read", "name": "retrieval.toml"})["values"]["retrieval"]["top_k"] == 12
