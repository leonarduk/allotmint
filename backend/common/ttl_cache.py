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

Concurrent misses on the same key are coalesced ("single-flight", #10360):
one caller builds and the rest wait for its result. Before this, every
concurrent miss ran its own multi-second build on its own worker thread, and
because those threads cannot be cancelled when the client disconnects,
repeated page views piled duplicate builds onto the AnyIO pool until every
sync route queued behind them.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Callable, Dict, Generic, Hashable, Optional, Tuple, TypeVar, cast

T = TypeVar("T")

CacheKey = Tuple[Hashable, ...]


class _InFlight(Generic[T]):
    """One in-progress build that concurrent callers for the same key wait on."""

    __slots__ = ("done", "value", "error", "builder_thread")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Optional[T] = None
        self.error: Optional[BaseException] = None
        self.builder_thread = threading.get_ident()


class TTLCache(Generic[T]):
    """Cache build results under a caller-supplied key for ``ttl_seconds``."""

    def __init__(self, ttl_seconds: float, *, name: str = "ttl_cache") -> None:
        self._ttl_seconds = ttl_seconds
        self._name = name
        self._entries: Dict[CacheKey, Tuple[float, T]] = {}
        self._in_flight: Dict[CacheKey, _InFlight[T]] = {}
        # Bumped by clear() so a build that started before the clear does not
        # store its (possibly stale) result afterwards.
        self._generation = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def get_or_build(self, key: CacheKey, build: Callable[[], T]) -> T:
        """Return a fresh cached value for ``key``, else build, store and return one.

        ``build`` is called outside the lock, so a slow build for one key never
        blocks callers for another. Concurrent misses on the *same* key wait
        for the first caller's build instead of starting their own; if that
        build raises, every waiter sees the error and nothing is cached, so
        the next call builds again. A ``build`` that re-enters
        ``get_or_build`` for its own key builds directly rather than waiting
        on itself.
        """

        with self._lock:
            cached = self._entries.get(key)
            flight = self._in_flight.get(key)
            is_builder = flight is None
            generation = self._generation
            fresh = cached is not None and time.monotonic() - cached[0] < self._ttl_seconds
            if not fresh and flight is None:
                flight = _InFlight()
                self._in_flight[key] = flight
        if fresh:
            return copy.deepcopy(cached[1])  # type: ignore[index]
        flight = cast("_InFlight[T]", flight)

        if is_builder:
            return self._build_as_leader(key, build, flight, generation)
        if flight.builder_thread == threading.get_ident():
            return build()
        flight.done.wait()
        if flight.error is not None:
            raise flight.error
        return copy.deepcopy(flight.value)  # type: ignore[arg-type]

    def _build_as_leader(self, key: CacheKey, build: Callable[[], T], flight: _InFlight[T], generation: int) -> T:
        """Run ``build`` for ``key``, publish the result to waiters, and cache it."""

        try:
            value = build()
        except BaseException as exc:
            flight.error = exc
            raise
        else:
            stored = copy.deepcopy(value)
            flight.value = stored
            with self._lock:
                if generation == self._generation:
                    self._entries[key] = (time.monotonic(), stored)
            return value
        finally:
            with self._lock:
                if self._in_flight.get(key) is flight:
                    del self._in_flight[key]
            flight.done.set()

    def clear(self) -> None:
        """Drop every entry. Safe to call when nothing is cached.

        A build already in progress still answers the callers waiting on it,
        but its result is not cached.
        """

        with self._lock:
            self._entries.clear()
            self._in_flight.clear()
            self._generation += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


__all__ = ["CacheKey", "TTLCache"]
