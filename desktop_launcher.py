"""Windows entry point for the portable ApexCode executable."""

from __future__ import annotations

import os
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


def main() -> None:
    root = bundle_root()
    os.chdir(root)
    frozen = bool(getattr(sys, "frozen", False))
    workspace = root / "workspace" if frozen else root
    workspace.mkdir(parents=True, exist_ok=True)
    settings = replace(Settings.from_env(workspace=workspace), config_file=root / ".env")
    application = create_app(settings)
    url = "http://127.0.0.1:8000"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"ApexCode 已启动：{url}")
    print(f"工作区：{settings.workspace}")
    uvicorn.run(application, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
