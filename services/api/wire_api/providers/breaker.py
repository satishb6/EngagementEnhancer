"""Per-provider circuit breaker: 5 failures in 60s opens for 5 minutes."""

import time
from collections import deque
from dataclasses import dataclass, field


class CircuitOpen(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    provider_id: str
    failure_threshold: int = 5
    window_s: float = 60.0
    open_duration_s: float = 300.0
    _failures: deque[float] = field(default_factory=deque)
    _opened_at: float | None = None

    def check(self) -> None:
        """Raise CircuitOpen if the breaker is open."""
        if self._opened_at is not None:
            if time.monotonic() - self._opened_at < self.open_duration_s:
                remaining = self.open_duration_s - (time.monotonic() - self._opened_at)
                raise CircuitOpen(
                    f"{self.provider_id} circuit open for another {remaining:.0f}s "
                    f"after {self.failure_threshold} failures"
                )
            # half-open: allow a try
            self._opened_at = None
            self._failures.clear()

    def record_success(self) -> None:
        self._failures.clear()

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures.append(now)
        while self._failures and now - self._failures[0] > self.window_s:
            self._failures.popleft()
        if len(self._failures) >= self.failure_threshold:
            self._opened_at = now

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None and (
            time.monotonic() - self._opened_at < self.open_duration_s
        )


_breakers: dict[str, CircuitBreaker] = {}


def breaker_for(provider_id: str) -> CircuitBreaker:
    if provider_id not in _breakers:
        _breakers[provider_id] = CircuitBreaker(provider_id)
    return _breakers[provider_id]
