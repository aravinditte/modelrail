"""Ollama adapter (spec 7.2) — optional local inference.

Local unavailability is a CONNECTION error (fallbackable), model problems are
classified separately. No assumption that all Ollama models share capabilities:
capabilities are declared per route, health comes from /api/tags.
"""

from __future__ import annotations

import httpx

from ..config import get_settings
from ..core.errors import ErrorClass, ProviderError
from ..domain.pricing import estimate_messages_tokens, estimate_tokens
from .base import CompletionRequest, CompletionResult, ProviderAdapter, StreamChunk, Usage


class OllamaProvider(ProviderAdapter):
    name = "ollama"

    def __init__(self, configuration: dict | None = None, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(configuration)
        self.base_url = (self.configuration.get("base_url") or get_settings().ollama_base_url).rstrip("/")
        self._transport = transport

    def capabilities(self) -> dict:
        return {"streaming": True, "chat": True, "deterministic": False, "local": True}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0, transport=self._transport) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def discover_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=3.0, transport=self._transport) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", [])]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        settings = get_settings()
        timeout = httpx.Timeout(request.timeout_s, connect=settings.provider_connect_timeout_s)
        payload = {"model": request.upstream_model, "messages": request.messages, "stream": False}
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException:
            raise ProviderError("ollama timed out", ErrorClass.TIMEOUT)
        except httpx.HTTPError:
            raise ProviderError("ollama is unreachable (local service unavailable)", ErrorClass.CONNECTION)
        if resp.status_code == 404:
            raise ProviderError("ollama model not found", ErrorClass.NOT_FOUND, status_code=404)
        if resp.status_code >= 400:
            cls = ErrorClass.SERVER if resp.status_code >= 500 else ErrorClass.BAD_REQUEST
            raise ProviderError(f"ollama returned HTTP {resp.status_code}", cls, status_code=resp.status_code)
        data = resp.json()
        content = ((data.get("message") or {}).get("content")) or ""
        if "prompt_eval_count" in data or "eval_count" in data:
            usage = Usage(
                input_tokens=int(data.get("prompt_eval_count", 0)),
                output_tokens=int(data.get("eval_count", 0)),
                source="provider_reported",
            )
        else:
            usage = Usage(
                input_tokens=estimate_messages_tokens(request.messages),
                output_tokens=estimate_tokens(content),
                source="estimated",
            )
        return CompletionResult(
            content=content,
            finish_reason="stop",
            usage=usage,
            provider_model=data.get("model") or request.upstream_model,
        )

    async def stream(self, request: CompletionRequest):
        result = await self.complete(request)
        words = result.content.split(" ")
        for i, w in enumerate(words):
            yield StreamChunk(content=(w if i == 0 else " " + w))
        yield StreamChunk(content="", finish_reason=result.finish_reason, usage=result.usage)
