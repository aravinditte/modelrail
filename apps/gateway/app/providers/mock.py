"""Deterministic mock provider (spec 7.1) — the reliability testbed.

Deterministic behaviour:
- Default output: "Mock response to: <last user message>" (truncated).
- "echo:<text>" as the last user message returns <text> verbatim.
- "[[script:KEY]]" anywhere returns the scripted response for KEY
  (from configuration["scripted"] or settings.mock_scripted_json).
- Failure injection, scoped by this instance's fail_key
  (configuration["fail_key"], default = provider name):
    [fail:<key>=timeout|rate_limit|auth|server|outage]
    [fail:<key>=flaky:N]  -> fail with a server error the first N times, then succeed
- "[mock:latency=NNN]" sleeps NNN ms before answering.
Usage is simulated but explicitly labelled source="simulated".
"""

from __future__ import annotations

import asyncio
import json
import re

from ..config import get_settings
from ..core.errors import ErrorClass, ProviderError
from ..domain.pricing import estimate_messages_tokens, estimate_tokens
from .base import CompletionRequest, CompletionResult, ProviderAdapter, StreamChunk, Usage

_FAIL_RE = re.compile(r"\[fail:([A-Za-z0-9_-]+)=([a-z_]+)(?::(\d+))?\]")
_LATENCY_RE = re.compile(r"\[mock:latency=(\d+)\]")
_SCRIPT_RE = re.compile(r"\[\[script:([A-Za-z0-9_-]+)\]\]")


class MockProvider(ProviderAdapter):
    name = "mock"
    _flaky_counters: dict[str, int] = {}

    @classmethod
    def reset(cls) -> None:
        cls._flaky_counters = {}

    @property
    def fail_key(self) -> str:
        return str(self.configuration.get("fail_key") or self.name)

    def _scripted(self) -> dict:
        scripted = dict(self.configuration.get("scripted") or {})
        raw = get_settings().mock_scripted_json
        if raw:
            try:
                scripted.update(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return scripted

    def capabilities(self) -> dict:
        return {"streaming": True, "chat": True, "deterministic": True}

    async def health_check(self) -> bool:
        return True

    def _last_user(self, request: CompletionRequest) -> str:
        for m in reversed(request.messages):
            if m.get("role") == "user":
                c = m.get("content") or ""
                return c if isinstance(c, str) else str(c)
        return ""

    async def _maybe_fail(self, request: CompletionRequest) -> None:
        text = self._last_user(request)
        m = _LATENCY_RE.search(text)
        if m:
            await asyncio.sleep(int(m.group(1)) / 1000.0)
        configured_latency = self.configuration.get("latency_ms")
        if configured_latency:
            await asyncio.sleep(float(configured_latency) / 1000.0)
        for key, kind, arg in _FAIL_RE.findall(text):
            if key != self.fail_key:
                continue
            if kind == "timeout":
                raise ProviderError("mock: simulated timeout", ErrorClass.TIMEOUT)
            if kind == "rate_limit":
                raise ProviderError(
                    "mock: simulated rate limit", ErrorClass.RATE_LIMIT, status_code=429, retry_after_s=0.01
                )
            if kind == "auth":
                raise ProviderError("mock: simulated provider auth failure", ErrorClass.AUTH, status_code=401)
            if kind == "server":
                raise ProviderError(
                    "mock: simulated provider server error", ErrorClass.SERVER, status_code=500
                )
            if kind == "outage":
                raise ProviderError("mock: simulated provider outage", ErrorClass.CONNECTION)
            if kind == "flaky":
                n = int(arg or "1")
                counter_key = f"{self.fail_key}:{id(request.messages)}:{text[:64]}"
                # deterministic per (fail_key, prompt) counter stored on the class
                counter_key = f"{self.fail_key}:{text[:128]}"
                seen = MockProvider._flaky_counters.get(counter_key, 0)
                MockProvider._flaky_counters[counter_key] = seen + 1
                if seen < n:
                    raise ProviderError("mock: simulated flaky failure", ErrorClass.SERVER, status_code=500)

    def _content(self, request: CompletionRequest) -> str:
        # Control markers are metadata, not content: strip them before the
        # script/echo/default logic so "[fail:x=...] echo: hi" echoes "hi".
        text = _FAIL_RE.sub("", _LATENCY_RE.sub("", self._last_user(request))).strip()
        sm = _SCRIPT_RE.search(text)
        if sm:
            scripted = self._scripted()
            if sm.group(1) in scripted:
                return str(scripted[sm.group(1)])
        if text.startswith("echo:"):
            return text[len("echo:") :].strip()
        return f"Mock response to: {text}"[:1000]

    def _usage(self, request: CompletionRequest, content: str) -> Usage:
        return Usage(
            input_tokens=estimate_messages_tokens(request.messages),
            output_tokens=max(1, estimate_tokens(content)),
            source="simulated",
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        await self._maybe_fail(request)
        content = self._content(request)
        return CompletionResult(
            content=content,
            finish_reason="stop",
            usage=self._usage(request, content),
            provider_model=request.upstream_model,
        )

    async def stream(self, request: CompletionRequest):
        await self._maybe_fail(request)
        content = self._content(request)
        words = content.split(" ")
        for i, w in enumerate(words):
            yield StreamChunk(content=(w if i == 0 else " " + w))
            await asyncio.sleep(0)
        yield StreamChunk(content="", finish_reason="stop", usage=self._usage(request, content))
