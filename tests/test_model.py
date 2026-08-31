import httpx
import pytest

from app.config import Settings
from app.model.client import ModelError, OpenAICompatibleClient, normalize_message


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


def test_normalize_legacy_and_structured_tool_arguments() -> None:
    legacy = normalize_message({"role": "assistant", "content": [{"type": "text", "text": "先检查"}], "function_call": {"name": "read_file", "arguments": {"path": "a.txt"}}})
    assert legacy["content"] == "先检查"
    assert legacy["tool_calls"][0]["function"]["arguments"] == '{"path": "a.txt"}'


def test_normalize_rejects_malformed_tool_call() -> None:
    with pytest.raises(ModelError):
        normalize_message({"role": "assistant", "tool_calls": [{"function": {"arguments": "{}"}}]})


def test_normalize_embedded_tool_use_and_json_envelope() -> None:
    embedded = normalize_message({"role": "assistant", "content": [{"type": "text", "text": "读取"}, {"type": "tool_use", "id": "x", "name": "read_file", "input": {"path": "a.txt"}}]})
    assert embedded["tool_calls"][0]["function"]["name"] == "read_file"
    envelope = normalize_message({"role": "assistant", "content": '{"tool_calls":[{"function":{"name":"read_file","arguments":{"path":"a.txt"}}}]}'})
    assert envelope["tool_calls"][0]["function"]["arguments"] == '{"path": "a.txt"}'
