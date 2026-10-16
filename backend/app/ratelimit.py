"""A sliding-window limiter per key (the clinic). Process-local: with several workers the limit is per worker.

Used for the export of reports (10 per minute per clinic, docs/api-contract.md). The moment comes from the
caller (the injected `now`), so tests are deterministic.
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends

from app.errors import rate_limited
from app.settings import Settings, get_settings

EXPORT_LIMIT = 10
EXPORT_WINDOW_SECONDS = 60


class SlidingWindowLimiter:
    def __init__(
        self, limit: int = EXPORT_LIMIT, window_seconds: int = EXPORT_WINDOW_SECONDS
    ) -> None:
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    def check(self, key: str, now: datetime) -> None:
        """Count a request of `key`; raise `rate_limited` (429, Retry-After) when the window is full."""
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            wait = int((hits[0] + self._window - now).total_seconds()) + 1
            raise rate_limited("Слишком много выгрузок подряд. Подождите немного.", wait)
        hits.append(now)


_export_limiters: dict[int, SlidingWindowLimiter] = {}


def get_export_limiter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SlidingWindowLimiter:
    """One limiter per configured limit (the limit comes from EXPORT_LIMIT_PER_MINUTE)."""
    limit = settings.export_limit_per_minute
    if limit not in _export_limiters:
        _export_limiters[limit] = SlidingWindowLimiter(limit=limit)
    return _export_limiters[limit]
