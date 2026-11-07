"""Configuration for default-on screen perception and application filters."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PerceptionConfig:
    allow_apps: frozenset[str] = frozenset()
    deny_apps: frozenset[str] = frozenset()
    hamming_threshold: int = 5

    def __post_init__(self) -> None:
        if self.hamming_threshold < 0:
            raise ValueError("hamming_threshold must be non-negative")
        if self.allow_apps & self.deny_apps:
            raise ValueError("allow_apps and deny_apps must be disjoint")


def load_perception_config(path: Path) -> PerceptionConfig:
    """Load app filters and hash threshold from the optional TOML file."""
    if not path.exists():
        return PerceptionConfig()
    with path.open("rb") as stream:
        raw = tomllib.load(stream).get("perception", {})
    return PerceptionConfig(
        allow_apps=frozenset(str(item).casefold() for item in raw.get("allow_apps", [])),
        deny_apps=frozenset(str(item).casefold() for item in raw.get("deny_apps", [])),
        hamming_threshold=int(raw.get("hamming_threshold", 5)),
    )
