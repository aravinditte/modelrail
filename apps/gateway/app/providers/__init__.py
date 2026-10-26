"""Provider registry. Route configuration selects and parameterises adapters."""

from __future__ import annotations

from .base import CompletionRequest, CompletionResult, ProviderAdapter, StreamChunk, Usage
from .mock import MockProvider
from .ollama import OllamaProvider
from .remote import RemoteProvider

_PROVIDERS = {
    "mock": MockProvider,
    "ollama": OllamaProvider,
    "remote": RemoteProvider,
}


def create_provider(name: str, configuration: dict | None = None) -> ProviderAdapter:
    cls = _PROVIDERS.get(name)
    if cls is None:
        # Unknown provider names are treated as additional mock instances so a
        # route chain can use several independently-configured mocks in tests
        # and demos (e.g. "mock-primary", "mock-secondary").
        if name.startswith("mock"):
            provider = MockProvider(configuration)
            provider.name = name  # type: ignore[misc]
            return provider
        raise ValueError(f"unknown provider: {name}")
    provider = cls(configuration)
    if name != provider.name:
        provider.name = name  # type: ignore[misc]
    return provider


__all__ = [
    "create_provider",
    "ProviderAdapter",
    "CompletionRequest",
    "CompletionResult",
    "StreamChunk",
    "Usage",
    "MockProvider",
    "OllamaProvider",
    "RemoteProvider",
]
