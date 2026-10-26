"""Unit tests: pricing, routing, circuit breaker, security, SSRF, mock, errors."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import ErrorClass, ProviderError
from app.core.security import generate_api_key, hash_api_key, verify_api_key
from app.domain.pricing import calculate_cost, estimate_tokens, reserve_estimate
from app.providers.mock import MockProvider
from app.providers.remote import validate_provider_url
from app.services.reliability import CircuitBreaker
from tests.conftest import add_route, make_project


# pricing -----------------------------------------------------------------
def test_cost_uses_decimal_and_quantises():
    cost = calculate_cost(1000, 500, Decimal("0.000001"), Decimal("0.000002"))
    assert cost == Decimal("0.00200000")
    assert isinstance(cost, Decimal)


def test_reserve_is_worst_case():
    reserve = reserve_estimate(10, 100, "0.001", "0.002")
    final = calculate_cost(10, 40, "0.001", "0.002")
    assert reserve >= final


def test_estimate_tokens_bounds():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 100) >= 25


# security ------------------------------------------------------------------
def test_api_key_hash_roundtrip():
    plaintext, prefix, key_hash = generate_api_key()
    assert plaintext.startswith("mr_live_")
    assert prefix == plaintext[:16]
    assert verify_api_key(plaintext, key_hash)
    assert not verify_api_key(plaintext + "x", key_hash)
    assert hash_api_key(plaintext) == key_hash
    assert plaintext not in key_hash


# circuit breaker -------------------------------------------------------------
def test_circuit_breaker_transitions():
    # Long open duration for the "stays open" assertion: wall-clock races
    # under load must not be able to expire the window mid-test.
    breaker = CircuitBreaker(failure_threshold=3, open_s=3600)
    assert breaker.state == "closed" and breaker.allow()
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state == "open" and not breaker.allow()
    # Short window for the half-open probe behaviour.
    probe = CircuitBreaker(failure_threshold=1, open_s=0.05)
    probe.record_failure()
    assert probe.state == "open"
    import time

    time.sleep(0.08)
    assert probe.allow() and probe.state == "half_open"
    probe.record_success()
    assert probe.state == "closed" and probe.consecutive_failures == 0


def test_circuit_breaker_half_open_failure_reopens():
    breaker = CircuitBreaker(failure_threshold=1, open_s=0.01)
    breaker.record_failure()
    assert breaker.state == "open"
    import time

    time.sleep(0.02)
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state == "open"


# provider error classification -------------------------------------------------
def test_error_retryable_matrix():
    assert ProviderError("x", ErrorClass.TIMEOUT).retryable
    assert ProviderError("x", ErrorClass.RATE_LIMIT).retryable
    assert ProviderError("x", ErrorClass.SERVER).retryable
    assert not ProviderError("x", ErrorClass.AUTH).retryable
    assert ProviderError("x", ErrorClass.AUTH).fallbackable
    assert not ProviderError("x", ErrorClass.BAD_REQUEST).fallbackable


# SSRF guard ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "https://10.0.0.5/v1",
        "ftp://example.com/v1",
        "https://metadata.google.internal/v1",
        "http://example.com/v1",  # plain http to a public host is not allowed
    ],
)
def test_ssrf_guard_rejects(url):
    with pytest.raises(ValueError):
        validate_provider_url(url)


def test_ssrf_guard_allows_https_public():
    validate_provider_url("https://api.openai.com/v1")


def test_ssrf_guard_allows_localhost_http():
    validate_provider_url("http://localhost:11434/v1")


# mock provider ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_deterministic_and_echo():
    provider = MockProvider({})
    from app.providers.base import CompletionRequest

    req = CompletionRequest(
        upstream_model="mock-1", messages=[{"role": "user", "content": "echo: deterministic"}]
    )
    first = await provider.complete(req)
    second = await provider.complete(req)
    assert first.content == second.content == "deterministic"
    assert first.usage.source == "simulated"


@pytest.mark.asyncio
async def test_mock_scripted_response():
    provider = MockProvider({"scripted": {"GREETING": "hello from script"}})
    from app.providers.base import CompletionRequest

    req = CompletionRequest(
        upstream_model="mock-1", messages=[{"role": "user", "content": "run [[script:GREETING]] now"}]
    )
    result = await provider.complete(req)
    assert result.content == "hello from script"


@pytest.mark.asyncio
async def test_mock_failure_markers_scoped_by_fail_key():
    provider = MockProvider({"fail_key": "primary"})
    other = MockProvider({"fail_key": "secondary"})
    from app.providers.base import CompletionRequest

    req = CompletionRequest(
        upstream_model="mock-1", messages=[{"role": "user", "content": "[fail:primary=server] hi"}]
    )
    with pytest.raises(ProviderError) as exc:
        await provider.complete(req)
    assert exc.value.error_class == ErrorClass.SERVER
    result = await other.complete(req)  # different fail_key: not triggered
    assert result.content


# routing ---------------------------------------------------------------------------
def test_routing_cost_orders_cheapest_first(db):
    make_project(db, routing_policy="cost")
    add_route(
        db,
        "alias-cost",
        provider="mock",
        priority=1,
        in_price="0.01",
        out_price="0.01",
        config={"fail_key": "a"},
    )
    add_route(
        db,
        "alias-cost",
        provider="mock-secondary",
        priority=2,
        in_price="0.001",
        out_price="0.001",
        config={"fail_key": "b"},
    )
    from app.services.routing import eligible_routes, order_routes

    routes = eligible_routes(db, "alias-cost", ["*"], streaming=False)
    ordered, meta = order_routes(db, routes, "cost", 100, 100)
    assert ordered[0].provider == "mock-secondary"
    assert len(meta) == 2 and all("estimated_cost" in m for m in meta)


def test_routing_excludes_disabled_and_disallowed(db):
    add_route(db, "alias-off", provider="mock", enabled=False)
    from app.services.routing import eligible_routes

    assert eligible_routes(db, "alias-off", ["*"], streaming=False) == []
    add_route(db, "alias-off", provider="mock")
    assert eligible_routes(db, "alias-off", ["other-alias"], streaming=False) == []
