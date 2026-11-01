"""Channel configuration for the chat channel and background slots.

Keys are never stored here. Each slot names an environment variable, and
the value is read from the host environment at load time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

PLACEHOLDER = "PLACEHOLDER_REPLACE_ME"


@dataclass(frozen=True)
class ChannelConfig:
    slot: str
    base_url: str
    model_id: str
    key_env: str
    enabled: bool = True

    def resolve_key(self) -> str | None:
        """Return the key from the environment, or None if unset or still a placeholder."""
        value = os.environ.get(self.key_env, "")
        if not value or value == PLACEHOLDER:
            return None
        return value
