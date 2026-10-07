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

    __slots__ = ("done", "value", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Optional[T] = None
        self.error: Optional[BaseException] = None


class TTLCache(Generic[T]):
    """Cache build results under a caller-supplied key for ``ttl_seconds``.

    Concurrency semantics (#10360):

    * **Single-flight.** The first miss for a key builds; every concurrent miss
      for that key waits for that build and gets a deep copy of its value, or
      its exception. A failed build caches nothing, so the next call rebuilds.
    * **Re-entrancy.** A ``build`` that calls ``get_or_build`` for a key that
      the *same thread* is already building (tracked per thread as the keys on
      its current call stack) cannot wait on itself without deadlocking, so
      the nested call runs its own ``build`` and returns that value directly.
      The nested value is neither published to the outer build's waiters nor
      cached; only the outer build's result is.
    * **clear().** Builds already in progress are detached, not cancelled: they
      still answer the callers already waiting on them, but their result is
      not cached, because it may predate the change that prompted the clear.
      A caller arriving *after* clear() therefore does not join a pre-clear
      build (it would be handed pre-clear data); it starts one fresh build that
      later callers coalesce onto. So per key, clear() can add at most one
      extra concurrent build, never one per caller.
    """

    def __init__(self, ttl_seconds: float, *, name: str = "ttl_cache") -> None:
        self._ttl_seconds = ttl_seconds
        self._name = name
        self._entries: Dict[CacheKey, Tuple[float, T]] = {}
        self._in_flight: Dict[CacheKey, _InFlight[T]] = {}
        # Bumped by clear() so a build that started before the clear does not
        # store its (possibly stale) result afterwards.
        self._generation = 0
        self._lock = threading.Lock()
        # Per-thread count of the keys this thread is building right now, for
        # the re-entrancy escape in get_or_build.
        self._local = threading.local()

    @property
    def name(self) -> str:
        return self._name

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def _keys_building_on_this_thread(self) -> Dict[CacheKey, int]:
        building: Optional[Dict[CacheKey, int]] = getattr(self._local, "building", None)
        if building is None:
            building = {}
            self._local.building = building
        return building

    def get_or_build(self, key: CacheKey, build: Callable[[], T]) -> T:
        """Return a fresh cached value for ``key``, else build, store and return one.

        ``build`` is called outside the lock, so a slow build for one key never
        blocks callers for another. See the class docstring for how concurrent
        misses, re-entrant calls and :meth:`clear` interact.
        """

        building = self._keys_building_on_this_thread()
        flight: Optional[_InFlight[T]] = None
        is_leader = False
        with self._lock:
            cached = self._entries.get(key)
            fresh = cached is not None and time.monotonic() - cached[0] < self._ttl_seconds
            if not fresh and key not in building:
                flight = self._in_flight.get(key)
                if flight is None:
                    flight = _InFlight()
                    self._in_flight[key] = flight
                    is_leader = True
            generation = self._generation

        if fresh:
            return copy.deepcopy(cast("Tuple[float, T]", cached)[1])
        if flight is None:
            # Re-entrant call from inside this thread's own build of ``key``:
            # waiting would deadlock, so build without publishing or caching.
            return build()
        if is_leader:
            return self._build_as_leader(key, build, flight, generation, building)
        flight.done.wait()
        if flight.error is not None:
            raise flight.error
        return copy.deepcopy(cast(T, flight.value))

    def _build_as_leader(
        self,
        key: CacheKey,
        build: Callable[[], T],
        flight: _InFlight[T],
        generation: int,
        building: Dict[CacheKey, int],
    ) -> T:
        """Run ``build`` for ``key``, publish the result to waiters, and cache it."""

        building[key] = building.get(key, 0) + 1
        try:
            value = build()
        except BaseException as exc:
            flight.error = exc
            raise
        else:
            # Waiters and the cache share this snapshot and each deep-copies it
            # on read; the leader returns its own ``value``, so mutating that
            # after return cannot leak into anyone else's result.
            stored = copy.deepcopy(value)
            flight.value = stored
            with self._lock:
                if generation == self._generation:
                    self._entries[key] = (time.monotonic(), stored)
            return value
        finally:
            building[key] -= 1
            if not building[key]:
                del building[key]
            with self._lock:
                if self._in_flight.get(key) is flight:
                    del self._in_flight[key]
            flight.done.set()

    def clear(self) -> None:
        """Drop every entry. Safe to call when nothing is cached.

        In-progress builds are detached rather than cancelled: they still
        answer the callers already waiting on them, but do not cache their
        result, and later callers start one fresh build instead of joining them.
        """

        with self._lock:
            self._entries.clear()
            self._in_flight.clear()
            self._generation += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


__all__ = ["CacheKey", "TTLCache"]
