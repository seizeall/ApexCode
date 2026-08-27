from pathlib import Path

import pytest

from app.config import Settings
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_read_and_search(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\nTODO: verify", encoding="utf-8")
    settings = Settings(workspace=tmp_path)
    registry = ToolRegistry(settings, lambda *_: _approved())
    read = await registry.call("read_file", {"path": "notes.txt"})
    hits = await registry.call("search_text", {"query": "todo"})
    assert read["ok"] and "hello" in read["content"]
    assert hits["ok"] and hits["hits"][0]["line"] == 2


async def _approved() -> bool:
    return True
