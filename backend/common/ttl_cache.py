"""A small, thread-safe TTL cache for expensive read-only computations.

Extracted per #7581 from the ad-hoc cache added to ``/opportunities`` in
#7575, so endpoints with the same shape -- a slow, deterministic build over
data that changes rarely -- do not each grow their own dict, lock and
staleness check.

Two rules this deliberately enforces for callers:

* **Values are deep-copied on the way in and on the way out.** A cached dict
  handed straight back would let one request's post-processing mutate what
  the next request sees. The copy costs milliseconds against builds measured
  in seconds (``/portfolio-group/all`` at 10.7s, #7215).
* **Nothing identity-dependent is cached under an identity-free key.** The
  cache cannot know what a key ought to contain, so callers must fold every
  input the build varies on into it -- including the caller's scope where the
  build consults request state. ``backend/common/portfolio_cache.py`` shows
  the pattern for a demo-scoped build.

TTL is the backstop, not the invalidation strategy: callers that know when
their data changes should call :meth:`TTLCache.clear` at that point.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Callable, Dict, Generic, Hashable, Tuple, TypeVar

T = TypeVar("T")

CacheKey = Tuple[Hashable, ...]


class TTLCache(Generic[T]):
    """Cache build results under a caller-supplied key for ``ttl_seconds``."""

    def __init__(self, ttl_seconds: float, *, name: str = "ttl_cache") -> None:
        self._ttl_seconds = ttl_seconds
        self._name = name
        self._entries: Dict[CacheKey, Tuple[float, T]] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def get_or_build(self, key: CacheKey, build: Callable[[], T]) -> T:
        """Return a fresh cached value for ``key``, else build, store and return one.

        ``build`` is called outside the lock. Two concurrent misses on the same
        key therefore both build, and the later one wins -- the same trade the
        #7575 cache makes. Holding the lock across a multi-second build would
        serialise every request in the process, including those for other keys,
        which is worse than an occasional duplicated build.
        """

        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
        if cached is not None:
            cached_at, value = cached
            if now - cached_at < self._ttl_seconds:
                return copy.deepcopy(value)

        value = build()
        with self._lock:
            self._entries[key] = (time.monotonic(), copy.deepcopy(value))
        return value

    def clear(self) -> None:
        """Drop every entry. Safe to call when nothing is cached."""

        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


__all__ = ["CacheKey", "TTLCache"]
