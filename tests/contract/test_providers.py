"""Provider contract tests (spec 17.3): the same contract runs against the
mock, the Ollama adapter (mock transport), and the remote adapter (mock
transport + disabled behaviour)."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import ErrorClass, ProviderError
from app.providers.base import CompletionRequest
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider
from app.providers.remote import RemoteProvider


def req(content="hello", model="test-model"):
    return CompletionRequest(
        upstream_model=model, messages=[{"role": "user", "content": content}], timeout_s=5
    )


@pytest.mark.asyncio
async def test_mock_contract():
    provider = MockProvider({})
    assert (await provider.health_check()) is True
    assert provider.capabilities()["streaming"] is True
    result = await provider.complete(req("echo: contract"))
    assert result.content == "contract" and result.usage.input_tokens > 0
    chunks = [c async for c in provider.stream(req("echo: a b"))]
    assert "".join(c.content for c in chunks) == "a b"
    assert chunks[-1].usage is not None


@pytest.mark.asyncio
async def test_ollama_contract_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.1"}]})
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "model": "llama3.1",
                    "message": {"role": "assistant", "content": "ollama says hi"},
                    "prompt_eval_count": 11,
                    "eval_count": 4,
                },
            )
        return httpx.Response(404, json={})

    provider = OllamaProvider({}, transport=httpx.MockTransport(handler))
    assert await provider.health_check() is True
    assert await provider.discover_models() == ["llama3.1"]
    result = await provider.complete(req())
    assert result.content == "ollama says hi"
    assert result.usage.source == "provider_reported"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 4)


@pytest.mark.asyncio
async def test_ollama_unavailable_is_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = OllamaProvider({}, transport=httpx.MockTransport(handler))
    assert await provider.health_check() is False
    with pytest.raises(ProviderError) as exc:
        await provider.complete(req())
    assert exc.value.error_class == ErrorClass.CONNECTION and exc.value.fallbackable


@pytest.mark.asyncio
async def test_remote_disabled_without_configuration():
    provider = RemoteProvider({})
    assert provider.enabled is False
    with pytest.raises(ProviderError):
        await provider.complete(req())


@pytest.mark.asyncio
async def test_remote_contract_with_mock_transport(monkeypatch):
    monkeypatch.setenv("REMOTE_PROVIDER_BASE_URL", "https://provider.example.com/v1")
    monkeypatch.setenv("REMOTE_PROVIDER_API_KEY", "sk-test-secret")
    from app.config import reset_settings

    reset_settings()
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer sk-test-secret"
            return httpx.Response(
                200,
                json={
                    "model": "remote-1",
                    "choices": [
                        {"message": {"role": "assistant", "content": "remote hi"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                },
            )

        provider = RemoteProvider({}, transport=httpx.MockTransport(handler))
        assert provider.enabled is True
        result = await provider.complete(req())
        assert result.content == "remote hi" and result.usage.source == "provider_reported"
    finally:
        reset_settings()


@pytest.mark.asyncio
async def test_remote_error_classification_and_no_secret_leak(monkeypatch):
    monkeypatch.setenv("REMOTE_PROVIDER_BASE_URL", "https://provider.example.com/v1")
    monkeypatch.setenv("REMOTE_PROVIDER_API_KEY", "sk-super-secret")
    from app.config import reset_settings

    reset_settings()
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "slow down"}, headers={"retry-after": "1"})

        provider = RemoteProvider({}, transport=httpx.MockTransport(handler))
        with pytest.raises(ProviderError) as exc:
            await provider.complete(req())
        assert exc.value.error_class == ErrorClass.RATE_LIMIT
        assert exc.value.retry_after_s == 1.0
        assert "sk-super-secret" not in str(exc.value)
    finally:
        reset_settings()
