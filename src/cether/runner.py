"""Wires screen capture, the vision describer, and the runtime event pause into one Perceiver.

One capture produces both the thumbnail (for hashing) and a PNG (for the
describer). The PNG lives in `FrameBuffer` only until the tick ends, and
`release` clears it on every tick, changed or not.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

from .perception import Perceiver, Thumbnail
from .vision import VisionConfig, VisionError, describe, load_vision_config

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class FrameBuffer:
    def __init__(self) -> None:
        self.png: bytes | None = None

    def clear(self) -> None:
        self.png = None


def http_post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise VisionError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc


def build_perceiver(
    *,
    vision_config_path: Path,
    world_log: Path,
    environ: Mapping[str, str],
    grab: Callable[[], tuple[Thumbnail, bytes]],
    foreground_app: Callable[[], str],
    post: Callable[[str, dict, dict], dict] = http_post,
) -> tuple[Perceiver, VisionConfig]:
    cfg = load_vision_config(vision_config_path, environ)
    frame = FrameBuffer()

    def capture() -> Thumbnail:
        thumb, png = grab()
        frame.png = png
        return thumb

    def describe_frame() -> str:
        if frame.png is None:
            raise VisionError("no frame to describe")
        return describe(cfg, frame.png, post)

    perceiver = Perceiver(
        capture=capture,
        describe=describe_frame,
        world_log=world_log,
        foreground_app=foreground_app,
        release=frame.clear,
    )
    return perceiver, cfg


def run_loop(
    perceiver: Perceiver,
    interval_seconds: float,
    should_stop: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    max_ticks: int | None = None,
) -> int:
    """Tick at a fixed interval until `should_stop` returns True. Return the tick count."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    ticks = 0
    while not should_stop():
        if max_ticks is not None and ticks >= max_ticks:
            break
        perceiver.tick()
        ticks += 1
        sleep(interval_seconds)
    return ticks
