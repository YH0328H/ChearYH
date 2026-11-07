from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.desktop import DesktopRuntime


def test_user_turn_interrupts_scheduled_sleep(tmp_path: Path) -> None:
    desktop = DesktopRuntime(tmp_path)
    runtime = desktop.runtime
    runtime.sleep_mode_provider = lambda _role, _now: "deep"
    sleeping = runtime.build_pipeline().tick()
    assert sleeping.perception["sleeping"] is True
    assert "reflection_calibration" in sleeping.background_results

    desktop.handle({"action": "send_message", "text": "wake up now"})
    awake = runtime.build_pipeline().tick()
    assert awake.perception["sleeping"] is False
    assert awake.perception["sleep_interrupted"] is True
    desktop.handle({"action": "shutdown"})
