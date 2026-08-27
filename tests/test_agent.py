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


@pytest.mark.asyncio
async def test_agent_returns_final_message(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("sample", encoding="utf-8")
    service = AgentService(Settings(workspace=tmp_path), model=FakeModel())
    events = []
    result, history = await service.run("检查文件", lambda *_: _approved(), lambda event: _collect(events, event))
    assert result == "已经读取并检查了文件。"
    assert any(event["type"] == "tool_result" for event in events)
    assert len(history) >= 4


async def _approved(*_args):
    return True


async def _collect(events, event):
    events.append(event)
