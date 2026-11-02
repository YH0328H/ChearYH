"""L1 narrative generation via the narrative slot (backend channel, structured dehydration only).

The narrative slot generates one L1 entry from a batch of L0 records when explicit
triggers fire (4.21): manual mark, relation event, high emotion/salience, or short-window
repetition. The prompt asks for a subjective narrative with emotion and relation tags.
"""

from __future__ import annotations

import json
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

Post = Callable[[str, dict, dict], dict]

PROMPT = """将以下对话片段生成一条主观叙事记录。要求：
1. 用第一人称视角，概括核心事件和感受
2. 标注情绪标签（如 calm, anxious, excited, sad 等）
3. 标注关系标签（如 user, self, third_party 等）
4. 叙事长度控制在 100 字以内

对话片段：
{records}

请以 JSON 格式返回，格式如下：
{{
  "narrative": "叙事文本",
  "emotion_tag": "情绪标签",
  "relation_tag": "关系标签"
}}
"""


@dataclass(frozen=True)
class NarrativeConfig:
    base_url: str
    model_id: str
    api_key: str


class NarrativeError(RuntimeError):
    pass


def load_narrative_config(path: Path, environ: Mapping[str, str]) -> NarrativeConfig:
    """Read the [narrative] table. The key comes from the environment, never from the file."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))["narrative"]
    return NarrativeConfig(
        base_url=str(raw["base_url"]),
        model_id=str(raw["model_id"]),
        api_key=environ.get(str(raw["key_env"]), ""),
    )


def generate_narrative(cfg: NarrativeConfig, l0_records: list[str], post: Post) -> dict:
    """Generate one L1 narrative from a batch of L0 records. Returns {narrative, emotion_tag, relation_tag}."""
    if not cfg.api_key:
        raise NarrativeError("API key is not set")
    records_text = "\n".join(f"- {r}" for r in l0_records)
    body = {
        "model": cfg.model_id,
        "messages": [{"role": "user", "content": PROMPT.format(records=records_text)}],
        "max_tokens": 512,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    try:
        reply = post(url, body, headers)
    except Exception as exc:
        raise NarrativeError(f"failed to call narrative slot: {exc}") from exc
    try:
        text = reply["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise NarrativeError(f"unexpected response shape: {json.dumps(reply, ensure_ascii=False)[:200]}") from exc
    if not isinstance(text, str) or not text.strip():
        raise NarrativeError("empty narrative")
    try:
        result = json.loads(text.strip())
        return {
            "narrative": str(result["narrative"]),
            "emotion_tag": result.get("emotion_tag"),
            "relation_tag": result.get("relation_tag"),
        }
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise NarrativeError(f"failed to parse narrative JSON: {text[:200]}") from exc
