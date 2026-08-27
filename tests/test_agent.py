import json
from pathlib import Path

import pytest

from app.agent.service import AgentService
from app.config import Settings


class FakeModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": json.dumps({"path": "sample.txt"})}}]}
        return {"role": "assistant", "content": "已经读取并检查了文件。"}


class ModeModel:
    def __init__(self) -> None:
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return {"role": "assistant", "content": "这是模式结果。"}


@pytest.mark.asyncio
async def test_agent_returns_final_message(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("sample", encoding="utf-8")
    service = AgentService(Settings(workspace=tmp_path), model=FakeModel())
    events = []
    result, history = await service.run("检查文件", lambda *_: _approved(), lambda event: _collect(events, event), mode="full")
    assert result == "已经读取并检查了文件。"
    assert any(event["type"] == "tool_result" for event in events)
    assert len(history) >= 4


async def _approved(*_args):
    return True


async def _collect(events, event):
    events.append(event)


@pytest.mark.asyncio
async def test_plan_mode_never_exposes_or_calls_tools(tmp_path: Path) -> None:
    model = ModeModel()
    events = []
    result, _ = await AgentService(Settings(workspace=tmp_path), model=model).run(
        "规划一个修复任务", _approved, lambda event: _collect(events, event), mode="plan"
    )
    assert result == "这是模式结果。"
    assert model.calls and model.calls[0][1] == []
    assert not any(event["type"] == "tool_start" for event in events)


@pytest.mark.asyncio
async def test_ask_mode_does_not_execute_tools(tmp_path: Path) -> None:
    model = ModeModel()
    events = []
    result, _ = await AgentService(Settings(workspace=tmp_path), model=model).run(
        "需求不清楚", _approved, lambda event: _collect(events, event), mode="ask"
    )
    assert result == "这是模式结果。"
    assert model.calls and model.calls[0][1] == []


@pytest.mark.asyncio
async def test_full_mode_uses_tools_without_approval_callback(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("sample", encoding="utf-8")
    model = FakeModel()
    approvals = []

    async def approval(*args):
        approvals.append(args)
        return False

    result, _ = await AgentService(Settings(workspace=tmp_path), model=model).run(
        "直接检查文件", approval, lambda event: _collect([], event), mode="full"
    )
    assert result == "已经读取并检查了文件。"
    assert approvals == []
