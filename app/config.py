from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for direct source use
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    workspace: Path = Path.cwd()
    max_steps: int = 12
    command_timeout: float = 30.0
    max_file_bytes: int = 512_000

    @classmethod
    def from_env(cls, workspace: str | Path | None = None) -> "Settings":
        if load_dotenv:
            load_dotenv()
        root = Path(workspace or os.getenv("CODING_AGENT_WORKSPACE", ".")).expanduser().resolve()
        return cls(
            api_key=os.getenv("CODING_AGENT_API_KEY", ""),
            base_url=os.getenv("CODING_AGENT_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("CODING_AGENT_MODEL", cls.model),
            workspace=root,
            max_steps=int(os.getenv("CODING_AGENT_MAX_STEPS", cls.max_steps)),
            command_timeout=float(os.getenv("CODING_AGENT_COMMAND_TIMEOUT", cls.command_timeout)),
        )
