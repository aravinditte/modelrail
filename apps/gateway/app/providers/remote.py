"""Optional OpenAI-compatible remote adapter (spec 7.3).

Disabled unless both base URL and API key are configured. Upstream URLs come
from server configuration ONLY — never from client requests — and are checked
by the SSRF guard. Credentials are never logged or embedded in errors.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..core.errors import ErrorClass, ProviderError
from ..domain.pricing import estimate_messages_tokens, estimate_tokens
from .base import CompletionRequest, CompletionResult, ProviderAdapter, StreamChunk, Usage


def validate_provider_url(url: str, allow_private: bool = False) -> None:
    """Reject unsafe upstream destinations. Raises ValueError with a safe message."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("provider URL must be an http(s) URL with a host")
    host = parsed.hostname
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1") and not allow_private:
        raise ValueError(
            "provider URL must use https unless it is a local/private endpoint explicitly allowed"
        )
    # Literal IP checks (metadata endpoints, loopback, link-local, private)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not allow_private:
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast:
            raise ValueError("provider URL host is a private/loopback/link-local address")
    if host == "metadata.google.internal":
        raise ValueError("provider URL host is blocked")


def classify_http_error(status: int) -> ErrorClass:
    if status in (401, 403):
        return ErrorClass.AUTH
    if status == 429:
        return ErrorClass.RATE_LIMIT
    if status >= 500:
        return ErrorClass.SERVER
    if status == 404:
        return ErrorClass.NOT_FOUND
    return ErrorClass.BAD_REQUEST


class RemoteProvider(ProviderAdapter):
    name = "remote"

    def __init__(self, configuration: dict | None = None, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(configuration)
        settings = get_settings()
        self.base_url = (
            self.configuration.get("base_url") or settings.remote_provider_base_url or ""
        ).rstrip("/")
        self.api_key = settings.remote_provider_api_key
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def capabilities(self) -> dict:
        return {"streaming": True, "chat": True, "deterministic": False, "enabled": self.enabled}

    async def health_check(self) -> bool:
        return self.enabled

    def _client(self, timeout_s: float) -> httpx.AsyncClient:
        settings = get_settings()
        timeout = httpx.Timeout(timeout_s, connect=settings.provider_connect_timeout_s)
        return httpx.AsyncClient(timeout=timeout, transport=self._transport, follow_redirects=False)

    def _check_enabled(self) -> None:
        if not self.enabled:
            raise ProviderError("remote provider is not configured", ErrorClass.CONNECTION)
        validate_provider_url(self.base_url, allow_private=get_settings().allow_private_provider_urls)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self._check_enabled()
        payload = {
            "model": request.upstream_model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        try:
            async with self._client(request.timeout_s) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.TimeoutException:
            raise ProviderError("remote provider timed out", ErrorClass.TIMEOUT)
        except httpx.HTTPError:
            raise ProviderError("remote provider connection failed", ErrorClass.CONNECTION)
        if resp.status_code >= 400:
            retry_after = None
            if resp.headers.get("retry-after"):
                try:
                    retry_after = float(resp.headers["retry-after"])
                except ValueError:
                    retry_after = None
            raise ProviderError(
                f"remote provider returned HTTP {resp.status_code}",
                classify_http_error(resp.status_code),
                status_code=resp.status_code,
                retry_after_s=retry_after,
            )
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content")) or ""
        raw_usage = data.get("usage") or {}
        if raw_usage:
            usage = Usage(
                input_tokens=int(raw_usage.get("prompt_tokens", 0)),
                output_tokens=int(raw_usage.get("completion_tokens", 0)),
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
            finish_reason=choice.get("finish_reason") or "stop",
            usage=usage,
            provider_model=data.get("model") or request.upstream_model,
        )

    async def stream(self, request: CompletionRequest):
        # Non-SSE-chunked simplification: fetch the completion, then emit word
        # chunks. Documented in docs/api — upstream streaming passthrough is a
        # future refinement; gateway-side SSE contract is unchanged.
        result = await self.complete(request)
        words = result.content.split(" ")
        for i, w in enumerate(words):
            yield StreamChunk(content=(w if i == 0 else " " + w))
        yield StreamChunk(content="", finish_reason=result.finish_reason, usage=result.usage)
