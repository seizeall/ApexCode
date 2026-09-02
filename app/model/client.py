from __future__ import annotations

import json
import asyncio
from typing import Any

import httpx

from app.config import Settings


class ModelError(RuntimeError):
    """An upstream model request failed or returned an unusable response."""


def _text_content(value: Any) -> str:
    """兼容 OpenAI 字符串内容和部分兼容服务返回的内容块。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(part.get("text", "")) for part in value if isinstance(part, dict) and part.get("type") in {"text", "output_text"})
    return "" if value is None else str(value)


def normalize_message(message: Any) -> dict[str, Any]:
    """将兼容接口的消息形状收敛为 Agent 使用的最小格式。"""
    if not isinstance(message, dict):
        raise ModelError("模型响应中的 message 不是对象。")
    role = message.get("role") or "assistant"
    if not isinstance(role, str):
        raise ModelError("模型响应中的 role 无效。")
    raw_content = message.get("content")
    normalized: dict[str, Any] = {"role": role, "content": _text_content(raw_content)}
    raw_calls = message.get("tool_calls")
    if raw_calls is None and isinstance(raw_content, list):
        embedded = [part for part in raw_content if isinstance(part, dict) and part.get("type") in {"tool_use", "function_call"}]
        if embedded:
            raw_calls = embedded
    if raw_calls is None and message.get("function_call"):
        raw_calls = [{"id": "legacy-function-call", "type": "function", "function": message["function_call"]}]
    if raw_calls is None and normalized["content"].lstrip().startswith(("{", "```json")):
        candidate = normalized["content"].strip()
        if candidate.startswith("```json") and candidate.endswith("```"):
            candidate = candidate[7:-3].strip()
        try:
            decoded = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            decoded = None
        if isinstance(decoded, dict) and isinstance(decoded.get("tool_calls"), list):
            raw_calls = decoded["tool_calls"]
            normalized["content"] = str(decoded.get("content") or "")
    if raw_calls is not None:
        if not isinstance(raw_calls, list):
            raise ModelError("模型响应中的 tool_calls 不是数组。")
        calls: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_calls):
            if not isinstance(raw, dict):
                raise ModelError("模型响应包含无效的工具调用。")
            fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
            name = fn.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ModelError("工具调用缺少名称。")
            arguments = fn.get("arguments", fn.get("input", {}))
            if isinstance(arguments, (dict, list)):
                arguments = json.dumps(arguments, ensure_ascii=False)
            elif not isinstance(arguments, str):
                raise ModelError("工具调用参数格式无效。")
            calls.append({"id": str(raw.get("id") or f"tool-call-{index + 1}"), "type": "function", "function": {"name": name, "arguments": arguments}})
        if calls:
            normalized["tool_calls"] = calls
    return normalized


class OpenAICompatibleClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.settings.api_key:
            raise ModelError("未配置 CODING_AGENT_API_KEY，无法请求模型。")
        if "anthropic" in self.settings.base_url.lower():
            payload, headers, endpoint = self._anthropic_request(messages, tools)
        else:
            payload = {"model": self.settings.model, "messages": messages, "temperature": 0.15, "tools": tools, "tool_choice": "auto"}
            if self.settings.model_max_tokens is not None:
                payload["max_tokens"] = self.settings.model_max_tokens
            headers = {"Authorization": f"Bearer {self.settings.api_key}"}
            endpoint = self.settings.base_url if self.settings.base_url.endswith("/chat/completions") else f"{self.settings.base_url}/chat/completions"
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.settings.model_timeout)
        try:
            last_error: Exception | None = None
            for attempt in range(self.settings.model_retries + 1):
                try:
                    response = await client.post(endpoint, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, dict) and isinstance(data.get("error"), dict):
                        raise ModelError(str(data["error"].get("message") or "模型返回了错误。"))
                    if "anthropic" in self.settings.base_url.lower():
                        return self._anthropic_response(data)
                    choices = data.get("choices") or []
                    if not choices or not isinstance(choices[0].get("message"), dict):
                        raise ModelError("模型响应缺少有效的 choices.message。")
                    return normalize_message(choices[0]["message"])
                except ModelError:
                    raise
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    last_error = exc
                    if attempt < self.settings.model_retries:
                        await asyncio.sleep(min(2 ** attempt, 4))
            if isinstance(last_error, ValueError):
                raise ModelError("模型返回的不是有效 JSON。") from last_error
            raise ModelError(f"模型请求失败：{last_error}") from last_error
        finally:
            if own_client:
                await client.aclose()

    def _anthropic_request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], str]:
        system = ""
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                system = str(message.get("content") or "")
            elif role == "tool":
                block = {"type": "tool_result", "tool_use_id": message.get("tool_call_id", ""), "content": message.get("content", "")}
                if converted and converted[-1].get("role") == "user" and isinstance(converted[-1].get("content"), list) and converted[-1]["content"] and converted[-1]["content"][0].get("type") == "tool_result":
                    converted[-1]["content"].append(block)
                else:
                    converted.append({"role": "user", "content": [block]})
            elif role == "assistant" and message.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                if message.get("content"):
                    blocks.append({"type": "text", "text": message["content"]})
                for call in message["tool_calls"]:
                    fn = call.get("function", {})
                    try:
                        arguments = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        arguments = {}
                    blocks.append({"type": "tool_use", "id": call.get("id", fn.get("name", "tool")), "name": fn.get("name", ""), "input": arguments})
                converted.append({"role": "assistant", "content": blocks})
            else:
                converted.append({"role": role, "content": message.get("content") or ""})
        anthropic_tools = [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "input_schema": t["function"].get("parameters", {"type": "object"})} for t in tools]
        payload: dict[str, Any] = {"model": self.settings.model, "messages": converted, "tools": anthropic_tools}
        if self.settings.model_max_tokens is not None:
            payload["max_tokens"] = self.settings.model_max_tokens
        if system:
            payload["system"] = system
        headers = {"x-api-key": self.settings.api_key, "anthropic-version": "2023-06-01"}
        if self.settings.base_url.endswith("/messages"):
            endpoint = self.settings.base_url
        elif self.settings.base_url.endswith("/v1"):
            endpoint = f"{self.settings.base_url}/messages"
        else:
            endpoint = f"{self.settings.base_url}/v1/messages"
        return payload, headers, endpoint

    def _anthropic_response(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ModelError("Anthropic 响应不是对象。")
        if isinstance(data.get("error"), dict):
            raise ModelError(str(data["error"].get("message") or "Anthropic 模型请求失败。"))
        if not isinstance(data.get("content"), list):
            raise ModelError("Anthropic 响应缺少有效的 content。")
        content = data.get("content") or []
        text_parts = [block.get("text", "") for block in content if block.get("type") == "text"]
        calls = []
        for block in content:
            if block.get("type") == "tool_use":
                calls.append({"id": block.get("id", block.get("name", "tool")), "type": "function", "function": {"name": block.get("name", ""), "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)}})
        message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
        if calls:
            message["tool_calls"] = calls
        return message
