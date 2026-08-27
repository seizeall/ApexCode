from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings
from app.model.client import ModelError, OpenAICompatibleClient
from app.tools.registry import ToolRegistry


EventSink = Callable[[dict[str, Any]], Awaitable[None]]


SYSTEM_PROMPT = """你是一个运行在本机工作区内的编程助手。先理解任务，再用工具检查真实文件；不要猜测文件内容。\n只有在确实需要时才修改文件或执行命令。每次工具调用后检查结果，遇到错误要解释原因并调整方案。完成后用简洁中文说明改动、验证方式和仍需用户注意的事项。"""


class AgentService:
    def __init__(self, settings: Settings, model: OpenAICompatibleClient | None = None) -> None:
        self.settings = settings
        self.model = model or OpenAICompatibleClient(settings)

    async def run(self, prompt: str, approve: Callable[[str, dict[str, Any]], Awaitable[bool]], emit: EventSink, history: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, Any]]]:
        messages = list(history or [])
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": prompt})
        registry = ToolRegistry(self.settings, approve)
        for step in range(1, self.settings.max_steps + 1):
            await emit({"type": "step", "step": step, "message": f"正在处理第 {step} 轮"})
            try:
                message = await self.model.complete(messages, registry.schemas())
            except ModelError as exc:
                await emit({"type": "error", "message": str(exc)})
                return str(exc), messages
            messages.append(message)
            content = message.get("content") or ""
            if content:
                await emit({"type": "assistant", "message": content})
            calls = message.get("tool_calls") or []
            if not calls:
                return content or "模型没有返回文本结果。", messages
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    result = {"ok": False, "error": "工具参数不是有效 JSON。"}
                else:
                    await emit({"type": "tool_start", "tool": name, "arguments": args})
                    result = await registry.call(name, args)
                    await emit({"type": "tool_result", "tool": name, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps(result, ensure_ascii=False)})
        await emit({"type": "error", "message": "达到最大执行轮数，任务已停止。"})
        return "达到最大执行轮数，任务已停止。", messages
