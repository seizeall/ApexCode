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
    model_timeout: float = 60.0
    max_file_bytes: int = 512_000
    max_upload_file_bytes: int = 10 * 1024 * 1024
    max_upload_total_bytes: int = 100 * 1024 * 1024
    max_context_chars: int = 80_000
    model_retries: int = 2
    max_tool_calls: int = 40
    session_file: Path | None = None
    config_file: Path | None = None

    def __post_init__(self) -> None:
        if self.session_file is None:
            object.__setattr__(self, "session_file", Path(self.workspace) / ".apexcode" / "sessions.json")
        if self.config_file is None:
            object.__setattr__(self, "config_file", Path(self.workspace) / ".env")

    @classmethod
    def from_env(cls, workspace: str | Path | None = None) -> "Settings":
        config_file = Path(os.getenv("CODING_AGENT_CONFIG_FILE", ".env")).expanduser().resolve()
        if load_dotenv:
            load_dotenv(config_file)
        root = Path(workspace or os.getenv("CODING_AGENT_WORKSPACE", ".")).expanduser().resolve()
        session_file = Path(os.getenv("CODING_AGENT_SESSION_FILE", str(root / ".apexcode" / "sessions.json"))).expanduser().resolve()
        return cls(
            api_key=os.getenv("CODING_AGENT_API_KEY", ""),
            base_url=os.getenv("CODING_AGENT_BASE_URL", cls.base_url).rstrip("/"),
            model=os.getenv("CODING_AGENT_MODEL", cls.model),
            workspace=root,
            max_steps=int(os.getenv("CODING_AGENT_MAX_STEPS", cls.max_steps)),
            command_timeout=float(os.getenv("CODING_AGENT_COMMAND_TIMEOUT", cls.command_timeout)),
            model_timeout=float(os.getenv("CODING_AGENT_MODEL_TIMEOUT", cls.model_timeout)),
            max_file_bytes=int(os.getenv("CODING_AGENT_MAX_FILE_BYTES", cls.max_file_bytes)),
            max_upload_file_bytes=int(os.getenv("CODING_AGENT_MAX_UPLOAD_FILE_BYTES", cls.max_upload_file_bytes)),
            max_upload_total_bytes=int(os.getenv("CODING_AGENT_MAX_UPLOAD_TOTAL_BYTES", cls.max_upload_total_bytes)),
            max_context_chars=int(os.getenv("CODING_AGENT_MAX_CONTEXT_CHARS", cls.max_context_chars)),
            model_retries=int(os.getenv("CODING_AGENT_MODEL_RETRIES", cls.model_retries)),
            max_tool_calls=int(os.getenv("CODING_AGENT_MAX_TOOL_CALLS", cls.max_tool_calls)),
            session_file=session_file,
            config_file=config_file,
        )
