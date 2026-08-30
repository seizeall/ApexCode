import httpx
import pytest

from app.config import Settings
from app.model.client import ModelError, OpenAICompatibleClient


@pytest.mark.asyncio
async def test_openai_response_is_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "完成"}}]})

    client = OpenAICompatibleClient(Settings(api_key="test", base_url="https://example.test/v1"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert (await client.complete([], []))["content"] == "完成"


@pytest.mark.asyncio
async def test_anthropic_tool_use_is_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "tool_use", "id": "call-1", "name": "read_file", "input": {"path": "a.txt"}}]})

    client = OpenAICompatibleClient(Settings(api_key="test", base_url="https://example.test/anthropic"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    message = await client.complete([], [])
    assert message["tool_calls"][0]["function"]["name"] == "read_file"


@pytest.mark.asyncio
async def test_model_retries_transport_failures() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "重试成功"}}]})

    client = OpenAICompatibleClient(Settings(api_key="test", base_url="https://example.test/v1", model_retries=1), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert (await client.complete([], []))["content"] == "重试成功"
    assert attempts == 2
