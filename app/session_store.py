from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class SessionStore:
    """Small atomic JSON store for local sessions; runtime data stays out of Git."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.metadata_path = path.with_name(f"{path.stem}.meta.json")
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
            self._write(self.path, data)

    async def metadata(self) -> dict[str, str]:
        async with self._lock:
            return self._read_metadata()

    async def rename(self, session_id: str, name: str) -> None:
        async with self._lock:
            names = self._read_metadata()
            names[session_id] = name
            self._write(self.metadata_path, names)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            data = self._read()
            data.pop(session_id, None)
            self._write(self.path, data)
            names = self._read_metadata()
            names.pop(session_id, None)
            self._write(self.metadata_path, names)

    def _write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def _read_metadata(self) -> dict[str, str]:
        if not self.metadata_path.is_file():
            return {}
        try:
            raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            return {key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)} if isinstance(raw, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
