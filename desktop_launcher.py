"""Windows entry point for the portable ApexCode executable."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from dataclasses import replace

from app.config import Settings
from app.web.app import create_app


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def available_port(preferred: int, attempts: int = 100) -> int:
    """Select the preferred localhost port or the next available one."""
    for port in range(preferred, min(preferred + attempts, 65_536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise OSError(f"端口 {preferred} 之后没有可用端口。")


def main() -> None:
    root = bundle_root()
    os.chdir(root)
    frozen = bool(getattr(sys, "frozen", False))
    configured = Settings.from_env()
    configured_workspace = os.getenv("CODING_AGENT_WORKSPACE", "").strip()
    workspace = Path(configured_workspace).expanduser().resolve() if configured_workspace else (root / "workspace" if frozen else root)
    workspace.mkdir(parents=True, exist_ok=True)
    settings = replace(configured, workspace=workspace, session_file=workspace / ".apexcode" / "sessions.json", config_file=root / ".env")
    application = create_app(settings)
    preferred_port = int(os.getenv("CODING_AGENT_PORT", "8000"))
    if not 1 <= preferred_port <= 65535:
        raise ValueError("CODING_AGENT_PORT 必须在 1 到 65535 之间。")
    port = available_port(preferred_port)
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"ApexCode 已启动：{url}")
    print(f"工作区：{settings.workspace}")
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
