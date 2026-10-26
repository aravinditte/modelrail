"""Shared provider contract (spec section 7).

Domain types only — no FastAPI objects, no provider-specific HTTP here.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class CompletionRequest:
    upstream_model: str
    messages: list[dict]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    seed: int | None = None
    request_id: str = ""
    timeout_s: float = 30.0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    source: str = "estimated"  # provider_reported|calculated|estimated|simulated|unknown


@dataclass
class CompletionResult:
    content: str
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)
    provider_model: str = ""


@dataclass
class StreamChunk:
    content: str = ""
    finish_reason: str | None = None
    usage: Usage | None = None


class ProviderAdapter(abc.ABC):
    name: str = "base"

    def __init__(self, configuration: dict | None = None):
        self.configuration = configuration or {}

    @abc.abstractmethod
    def capabilities(self) -> dict: ...

    @abc.abstractmethod
    async def health_check(self) -> bool: ...

    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    @abc.abstractmethod
    async def stream(self, request: CompletionRequest):  # async generator of StreamChunk
        ...

    def normalize_usage(self, raw_input: int | None, raw_output: int | None, source: str) -> Usage:
        return Usage(input_tokens=raw_input or 0, output_tokens=raw_output or 0, source=source)

    async def close(self) -> None:
        return None
