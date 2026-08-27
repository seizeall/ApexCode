from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings


class ModelError(RuntimeError):
    """An upstream model request failed or returned an unusable response."""


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
            headers = {"Authorization": f"Bearer {self.settings.api_key}"}
            endpoint = f"{self.settings.base_url}/chat/completions"
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "anthropic" in self.settings.base_url.lower():
                return self._anthropic_response(data)
            choices = data.get("choices") or []
            if not choices or "message" not in choices[0]:
                raise ModelError("模型响应缺少 choices.message。")
            return choices[0]["message"]
        except httpx.HTTPError as exc:
            raise ModelError(f"模型请求失败：{exc}") from exc
        except ValueError as exc:
            raise ModelError("模型返回的不是有效 JSON。") from exc
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
                converted.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": message.get("tool_call_id", ""), "content": message.get("content", "")} ]})
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
        payload: dict[str, Any] = {"model": self.settings.model, "max_tokens": 4096, "messages": converted, "tools": anthropic_tools}
        if system:
            payload["system"] = system
        headers = {"x-api-key": self.settings.api_key, "anthropic-version": "2023-06-01"}
        endpoint = f"{self.settings.base_url}/v1/messages" if not self.settings.base_url.endswith("/v1") else f"{self.settings.base_url}/messages"
        return payload, headers, endpoint

    def _anthropic_response(self, data: dict[str, Any]) -> dict[str, Any]:
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
