"""Circuit breaker timing and cost estimation accuracy."""

import pytest

from wire_api.providers.base import Capability
from wire_api.providers.breaker import CircuitBreaker, CircuitOpen
from wire_api.providers.costs import estimate_cost


def test_breaker_opens_after_five_failures_in_window() -> None:
    breaker = CircuitBreaker("test", failure_threshold=5, window_s=60, open_duration_s=300)
    for _ in range(4):
        breaker.record_failure()
    breaker.check()  # still closed
    breaker.record_failure()
    assert breaker.is_open
    with pytest.raises(CircuitOpen):
        breaker.check()


def test_breaker_success_resets_window() -> None:
    breaker = CircuitBreaker("test")
    for _ in range(4):
        breaker.record_failure()
    breaker.record_success()
    for _ in range(4):
        breaker.record_failure()
    assert not breaker.is_open


def test_video_estimate_is_per_second() -> None:
    twenty = estimate_cost(Capability.VIDEO, {"duration_s": 20})
    ten = estimate_cost(Capability.VIDEO, {"duration_s": 10})
    assert twenty == pytest.approx(2 * ten)
    # ~$2 for a 20s short — the number the whole tier table hangs off
    assert 100 <= twenty <= 400


def test_every_capability_estimates_without_running() -> None:
    for cap in Capability:
        assert estimate_cost(cap, {}) >= 0.0


def test_image_estimate_scales_with_n() -> None:
    one = estimate_cost(Capability.IMAGE, {"n": 1})
    three = estimate_cost(Capability.IMAGE, {"n": 3})
    assert three == pytest.approx(3 * one)
