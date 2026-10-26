"""Project rate limiting and concurrency governance (spec section 11).

In-process sliding-window implementation; when REDIS_URL is configured the
same interface can be backed by Redis (documented in operations.md). Budget
enforcement does NOT depend on this limiter or on Redis — it is enforced
transactionally in the database (budget.py), so a limiter/Redis outage can
never silently make budget enforcement permissive.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._tokens: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._inflight: dict[str, int] = defaultdict(int)

    def _prune(self, dq: deque, now: float) -> None:
        while dq and now - (dq[0][0] if isinstance(dq[0], tuple) else dq[0]) >= 60.0:
            dq.popleft()

    def check_and_record(self, project_id: str, rpm: int, tpm: int, est_tokens: int) -> str | None:
        """Returns an error code string if limited, else None (and records)."""
        now = time.monotonic()
        with self._lock:
            rq = self._requests[project_id]
            self._prune(rq, now)
            if len(rq) >= rpm:
                return "rate_limit_requests"
            tq = self._tokens[project_id]
            self._prune(tq, now)
            if sum(t for _, t in tq) + est_tokens > tpm:
                return "rate_limit_tokens"
            rq.append(now)
            tq.append((now, est_tokens))
            return None

    def acquire_concurrency(self, project_id: str, max_concurrency: int) -> bool:
        with self._lock:
            if self._inflight[project_id] >= max_concurrency:
                return False
            self._inflight[project_id] += 1
            return True

    def release_concurrency(self, project_id: str) -> None:
        with self._lock:
            if self._inflight[project_id] > 0:
                self._inflight[project_id] -= 1

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._tokens.clear()
            self._inflight.clear()


LIMITER = RateLimiter()
