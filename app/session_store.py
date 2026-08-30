from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class SessionStore:
    """Small atomic JSON store for local sessions; runtime data stays out of Git."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self) -> dict[str, list[dict[str, Any]]]:
        async with self._lock:
            return self._read()

    async def get(self, session_id: str) -> list[dict[str, Any]]:
        data = await self.load()
        return data.get(session_id, [])

    async def save(self, session_id: str, history: list[dict[str, Any]]) -> None:
        async with self._lock:
            data = self._read()
            data[session_id] = history
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
