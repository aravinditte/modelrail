"""Retry policy and circuit breaker (spec section 9).

Circuit breaker states: closed -> open (after N consecutive failures) ->
half-open (after the open duration, one probe) -> closed (probe succeeds) or
open again (probe fails). State is in-process per (provider, upstream model);
metrics count every transition.
"""

from __future__ import annotations

import random
import time

from ..config import get_settings


class CircuitBreaker:
    def __init__(self, failure_threshold: int | None = None, open_s: float | None = None):
        settings = get_settings()
        self.failure_threshold = failure_threshold or settings.circuit_failure_threshold
        self.open_s = open_s if open_s is not None else settings.circuit_open_s
        self.state = "closed"
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.transitions = 0

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.opened_at is not None and (time.monotonic() - self.opened_at) >= self.open_s:
                self.state = "half_open"
                self.transitions += 1
                return True
            return False
        return True  # half_open: allow a probe

    def record_success(self) -> None:
        if self.state != "closed":
            self.transitions += 1
        self.state = "closed"
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.state == "half_open" or self.consecutive_failures >= self.failure_threshold:
            if self.state != "open":
                self.transitions += 1
            self.state = "open"
            self.opened_at = time.monotonic()


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, provider: str, upstream_model: str) -> CircuitBreaker:
        key = f"{provider}:{upstream_model}"
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker()
        return self._breakers[key]

    def states(self) -> dict[str, str]:
        return {k: b.state for k, b in self._breakers.items()}

    def reset(self) -> None:
        self._breakers = {}


BREAKERS = CircuitBreakerRegistry()


def backoff_delay(attempt: int, retry_after_s: float | None = None) -> float:
    """Exponential backoff with jitter, honouring Retry-After (capped)."""
    settings = get_settings()
    if retry_after_s is not None:
        return min(retry_after_s, settings.retry_max_delay_s)
    base = settings.retry_base_delay_s * (2 ** max(0, attempt - 1))
    return min(base, settings.retry_max_delay_s) * (0.5 + random.random() * 0.5)
