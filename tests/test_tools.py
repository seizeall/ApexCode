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


@pytest.mark.asyncio
async def test_apply_patch_requires_approval_and_updates_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    registry = ToolRegistry(Settings(workspace=tmp_path), lambda *_: _approved())
    result = await registry.call("apply_patch", {"patch": "*** Begin Patch\n*** Update File: sample.txt\n@@\n one\n-two\n+changed\n*** End Patch"})
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "one\nchanged\n"


@pytest.mark.asyncio
async def test_apply_patch_rejects_delete_and_mismatch(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("one\n", encoding="utf-8")
    registry = ToolRegistry(Settings(workspace=tmp_path), lambda *_: _approved())
    deleted = await registry.call("apply_patch", {"patch": "*** Begin Patch\n*** Delete File: sample.txt\n*** End Patch"})
    mismatch = await registry.call("apply_patch", {"patch": "*** Begin Patch\n*** Update File: sample.txt\n@@\n missing\n+new\n*** End Patch"})
    assert deleted["ok"] is False and "删除" in deleted["error"]
    assert mismatch["ok"] is False and "不匹配" in mismatch["error"]


@pytest.mark.asyncio
async def test_apply_patch_accepts_standard_unified_diff(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    registry = ToolRegistry(Settings(workspace=tmp_path), lambda *_: _approved())
    patch = "--- a/sample.txt\n+++ b/sample.txt\n@@ -1,2 +1,2 @@\n one\n-two\n+changed\n"
    result = await registry.call("apply_patch", {"patch": patch})
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "one\nchanged\n"


@pytest.mark.asyncio
async def test_apply_patch_can_add_a_new_file(tmp_path: Path) -> None:
    registry = ToolRegistry(Settings(workspace=tmp_path), lambda *_: _approved())
    result = await registry.call("apply_patch", {"patch": "*** Begin Patch\n*** Add File: created.txt\n+hello\n+world\n*** End Patch"})
    assert result["ok"] is True
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "hello\nworld\n"
