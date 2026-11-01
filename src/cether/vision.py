"""Screen description through an OpenAI-compatible chat endpoint with image input.

The transport is injected so tests run without network. The caller passes
PNG bytes already held in memory. Nothing here writes the image to disk.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass

Post = Callable[[str, dict, dict], dict]  # (url, json_body, headers) -> parsed JSON

PROMPT = "用一句简短的中文描述这张屏幕截图的主要内容，不要猜测截图中看不到的信息。"


@dataclass(frozen=True)
class VisionConfig:
    base_url: str
    model_id: str
    api_key: str


class VisionError(RuntimeError):
    pass


def build_request(cfg: VisionConfig, png_bytes: bytes) -> tuple[str, dict, dict]:
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    body = {
        "model": cfg.model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 120,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    return url, body, headers


def describe(cfg: VisionConfig, png_bytes: bytes, post: Post) -> str:
    if not cfg.api_key:
        raise VisionError("API key is not set")
    url, body, headers = build_request(cfg, png_bytes)
    reply = post(url, body, headers)
    try:
        text = reply["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionError(f"unexpected response shape: {json.dumps(reply, ensure_ascii=False)[:200]}") from exc
    if not isinstance(text, str) or not text.strip():
        raise VisionError("empty description")
    return text.strip()
