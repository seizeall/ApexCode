import asyncio
import json
from pathlib import Path

import pytest

from app.agent.service import AgentService, await_with_progress, compact_tool_arguments, compact_tool_result, trim_context
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
    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["result"]["content_chars"] == 6
    assert "content" not in tool_result["result"]
    assert len(history) >= 4


async def _approved(*_args):
    return True


async def _collect(events, event):
    events.append(event)


def test_trim_context_keeps_system_and_newest_messages() -> None:
    messages = [{"role": "system", "content": "system"}] + [{"role": "user", "content": "x" * 20 + str(i)} for i in range(8)]
    trimmed = trim_context(messages, 70)
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"].endswith("7")
    assert len(trimmed) < len(messages)


def test_system_prompt_requests_auditable_summary_without_private_reasoning() -> None:
    from app.agent.service import SYSTEM_PROMPT

    assert "可审计的工作摘要" in SYSTEM_PROMPT
    assert "不输出逐字内部推理" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_slow_work_emits_progress_heartbeats() -> None:
    events = []
    result = await await_with_progress(
        asyncio.sleep(.035, result="done"),
        lambda event: _collect(events, event),
        "正在等待测试任务",
        interval=.005,
    )
    assert result == "done"
    assert any(event["type"] == "progress" and event["elapsed_seconds"] >= 1 for event in events)


def test_tool_audit_events_are_compact() -> None:
    arguments = compact_tool_arguments("write_file", {"path": "site/index.html", "content": "x" * 2000})
    result = compact_tool_result("run_command", {"ok": True, "returncode": 0, "stdout": "x" * 2000, "stderr": ""})
    assert arguments == {"path": "site/index.html", "content_bytes": 2000}
    assert len(result["stdout_tail"]) == 800
    assert "stdout" not in result


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
