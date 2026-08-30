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


@pytest.mark.asyncio
async def test_tool_arguments_are_validated(tmp_path: Path) -> None:
    registry = ToolRegistry(Settings(workspace=tmp_path), lambda *_: _approved())
    result = await registry.call("read_file", {})
    assert result["ok"] is False
    assert "path" in result["error"]


@pytest.mark.asyncio
async def test_running_command_can_be_cancelled(tmp_path: Path) -> None:
    import asyncio
    cancel = asyncio.Event()
    registry = ToolRegistry(Settings(workspace=tmp_path, command_timeout=10), lambda *_: _approved(), cancel)
    task = asyncio.create_task(registry.call("run_command", {"command": 'python -c "import time; time.sleep(3)"'}))
    await asyncio.sleep(.15)
    cancel.set()
    result = await task
    assert result["cancelled"] is True
