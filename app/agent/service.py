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

    async def run(self, prompt: str, approve: Callable[[str, dict[str, Any]], Awaitable[bool]], emit: EventSink, history: list[dict[str, Any]] | None = None, mode: str = "ask") -> tuple[str, list[dict[str, Any]]]:
        messages = list(history or [])
        mode = mode if mode in {"full", "plan", "ask"} else "ask"
        mode_prompt = SYSTEM_PROMPT
        if mode == "plan":
            mode_prompt += "\n当前是计划模式：只输出分阶段执行计划、涉及文件和验证方式，不调用工具，不修改任何内容。"
        elif mode == "ask":
            mode_prompt += "\n当前是询问模式：先检查用户需求是否明确，只提出完成任务所必需的澄清问题，不调用工具，不修改任何内容。"
        else:
            mode_prompt += "\n当前是完全模式：在安全规则允许的前提下直接完成任务，不为普通文件写入和命令执行请求用户确认。"
        if messages and messages[0].get("role") == "system":
            messages[0] = {"role": "system", "content": mode_prompt}
        else:
            messages.insert(0, {"role": "system", "content": mode_prompt})
        messages.append({"role": "user", "content": prompt})
        registry = ToolRegistry(self.settings, approve)
        if mode in {"plan", "ask"}:
            await emit({"type": "step", "step": 1, "message": "正在整理需求" if mode == "plan" else "正在确认需求"})
            try:
                message = await self.model.complete(messages, [])
            except ModelError as exc:
                await emit({"type": "error", "message": str(exc)})
                return str(exc), messages
            messages.append(message)
            content = message.get("content") or "模型没有返回文本结果。"
            await emit({"type": "assistant", "message": content})
            return content, messages
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
