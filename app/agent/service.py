from __future__ import annotations

import json
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings
from app.model.client import ModelError, OpenAICompatibleClient, normalize_message
from app.tools.registry import ToolRegistry


EventSink = Callable[[dict[str, Any]], Awaitable[None]]


class AgentCancelled(RuntimeError):
    """The user cancelled the current task."""


SYSTEM_PROMPT = """你是一个运行在本机工作区内的编程助手。先理解任务，再用工具检查真实文件；不要猜测文件内容。\n只有在确实需要时才修改文件或执行命令。工具调用前可以输出简短、可审计的工作摘要，只陈述当前目标、关键决定和下一步，不输出逐字内部推理。每次工具调用后检查结果，遇到错误要解释原因并调整方案。完成后用简洁中文说明改动、验证方式和仍需用户注意的事项。"""


def trim_context(messages: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep the system prompt and newest conversation turns within a character budget."""
    if sum(len(str(item.get("content", ""))) for item in messages) <= limit:
        return messages
    system = messages[:1] if messages and messages[0].get("role") == "system" else []
    rest = messages[1:] if system else messages
    kept: list[dict[str, Any]] = []
    used = sum(len(str(item.get("content", ""))) for item in system)
    for item in reversed(rest):
        size = len(str(item.get("content", "")))
        if kept and used + size > limit:
            break
        kept.append(item)
        used += size
    kept.reverse()
    return system + kept


class AgentService:
    def __init__(self, settings: Settings, model: OpenAICompatibleClient | None = None) -> None:
        self.settings = settings
        self.model = model or OpenAICompatibleClient(settings)

    async def run(self, prompt: str, approve: Callable[[str, dict[str, Any]], Awaitable[bool]], emit: EventSink, history: list[dict[str, Any]] | None = None, mode: str = "ask", cancel_event: asyncio.Event | None = None) -> tuple[str, list[dict[str, Any]]]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("任务不能为空。")
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
        registry = ToolRegistry(self.settings, approve, cancel_event)
        tool_calls_used = sum(1 for item in messages if item.get("role") == "tool")
        if mode in {"plan", "ask"}:
            await emit({"type": "step", "step": 1, "message": "正在整理需求" if mode == "plan" else "正在确认需求"})
            messages = trim_context(messages, self.settings.max_context_chars)
            try:
                message = normalize_message(await self.model.complete(messages, []))
            except ModelError as exc:
                await emit({"type": "error", "message": str(exc)})
                return str(exc), messages
            messages.append(message)
            content = message.get("content") or "模型没有返回文本结果。"
            await emit({"type": "assistant", "message": content})
            return content, messages
        for step in range(1, self.settings.max_steps + 1):
            if cancel_event and cancel_event.is_set():
                await emit({"type": "cancelled", "message": "任务已取消。"})
                return "任务已取消。", messages
            await emit({"type": "step", "step": step, "message": f"正在处理第 {step} 轮"})
            before_trim = len(messages)
            messages = trim_context(messages, self.settings.max_context_chars)
            if len(messages) < before_trim:
                await emit({"type": "context_trimmed", "message": "历史消息较长，已保留最近上下文。"})
            try:
                message = normalize_message(await self.model.complete(messages, registry.schemas()))
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
            if tool_calls_used + len(calls) > self.settings.max_tool_calls:
                await emit({"type": "error", "message": "工具调用次数达到上限，任务已停止。"})
                return "工具调用次数达到上限，任务已停止。", messages
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                if not name:
                    result = {"ok": False, "error": "工具调用缺少名称。"}
                    await emit({"type": "tool_result", "tool": "unknown", "result": result})
                    messages.append({"role": "tool", "tool_call_id": call.get("id", "unknown"), "content": json.dumps(result, ensure_ascii=False)})
                    tool_calls_used += 1
                    continue
                try:
                    raw_args = fn.get("arguments") or "{}"
                    args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
                    if not isinstance(args, dict):
                        raise ValueError("工具参数必须是 JSON 对象。")
                except (json.JSONDecodeError, TypeError, ValueError):
                    result = {"ok": False, "error": "工具参数不是有效 JSON。"}
                else:
                    await emit({"type": "tool_start", "tool": name, "arguments": args})
                result = await registry.call(name, args)
                await emit({"type": "tool_result", "tool": name, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps(result, ensure_ascii=False)})
                tool_calls_used += 1
                if result.get("cancelled"):
                    return result.get("error", "用户取消了操作。"), messages
        await emit({"type": "error", "message": "达到最大执行轮数，任务已停止。"})
        return "达到最大执行轮数，任务已停止。", messages
