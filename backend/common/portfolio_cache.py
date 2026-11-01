"""Process-wide cache for built group portfolios.

``build_group_portfolio`` walks every owner's accounts and enriches every
holding with a price, and six endpoints call it on the way to their own cheap
aggregation -- ``/portfolio-group/{slug}`` and its ``/instruments``,
``/sectors``, ``/regions``, ``/exposure`` siblings. It was measured at 10.7s
for the ``all`` group (#7215) and had no cache at any layer, so a page that
touches several of those endpoints paid it several times over.

This lives in ``common`` rather than in ``routes/portfolio.py`` because the
write paths that must invalidate it (``backend/common/accounts_store.py``)
sit below the route layer; importing the route module from a store would be a
cycle.

Invalidation
------------
The TTL is a backstop for anything that changes the underlying data without
telling us. The paths that *do* know are expected to call
:func:`invalidate_group_portfolios` directly, so a user who adds a position
never sees their own write missing from the next page load:

* every committed account-document write (both accounts stores)
* holdings rebuilt from transactions
* an explicit price refresh
* approvals and user-config edits, both of which feed ``enrich_holding``

Scoping -- read before adding a caller
--------------------------------------
``build_group_portfolio`` is **not** identity-independent. It reaches
``data_loader.list_plots()``, which filters to ``config.demo_link_owner``
alone when :func:`backend.auth.is_demo_request` is true (see the #7408 note in
``_list_local_plots``). Caching one caller's result under a key that ignores
that would serve a demo-link visitor every real owner's holdings -- exactly
the leak #7402 closed. :func:`group_portfolio_cache_key` therefore folds the
caller's scope in (:func:`access_scope`), and every caller must use it rather
than assembling a key of its own.

With ``ENFORCE_OWNER_ACCESS`` on (#11087) ``list_plots()`` also filters a real
user's owners by ``email``/``viewers``, so the scope then names the
request's identity too: two users with different viewer rights never share
an entry, and a request with no identity gets its own (empty) one.

Shared performance inputs (#10755)
----------------------------------
The Performance page fires alpha, tracking error, max drawdown, the value
history, TWR and XIRR in parallel, and each handler used to rebuild the same
owner portfolio, holding value series and ledger replay for itself -- on a
cold cache the set ran past the client's 30s timeout. :func:`memoised` lets
``portfolio_utils`` share those intermediate builds across the requests,
single-flighted so concurrent requests wait for one build rather than each
running their own. It only caches inside :func:`sharing_performance_inputs`,
which the ``/performance`` routes enter, so other callers (reports, bots,
direct unit tests that monkeypatch the data between calls) keep computing
fresh. It is cleared alongside the group portfolios by
:func:`invalidate_group_portfolios`, so every write path above covers it.
"""

from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Hashable, Iterator, Optional, TypeVar

from backend.common.ttl_cache import CacheKey, TTLCache

# Long enough to collapse the several calls a single page load makes, short
# enough that anything which changes the data without invalidating explicitly
# (an out-of-band edit to the account files, say) self-corrects in about a
# minute. Matches the TTL #7575 chose for /opportunities.
GROUP_PORTFOLIO_TTL_SECONDS = 60.0
PERFORMANCE_INPUTS_TTL_SECONDS = 60.0

_T = TypeVar("_T")

_GROUP_PORTFOLIO_CACHE: TTLCache[Dict[str, Any]] = TTLCache(
    GROUP_PORTFOLIO_TTL_SECONDS,
    name="group_portfolio",
)

# Values of mixed type (portfolio dicts, pandas series, ledger rebuilds), so
# the cache is untyped; ``memoised`` restores the caller's type.
_PERFORMANCE_INPUTS_CACHE: TTLCache[Any] = TTLCache(
    PERFORMANCE_INPUTS_TTL_SECONDS,
    name="performance_inputs",
)

_SHARING_PERFORMANCE_INPUTS: ContextVar[bool] = ContextVar("sharing_performance_inputs", default=False)


def _demo_scope() -> Optional[str]:
    """Return the owner a demo-scoped request is confined to, else ``None``.

    Imported lazily for the same reason ``data_loader`` does it: ``backend.auth``
    imports back into ``backend.common``.
    """

    from backend.auth import is_demo_request
    from backend.config import config

    if not is_demo_request():
        return None
    demo_owner = config.demo_link_owner
    # An unresolvable demo owner still has to key differently from a normal
    # request -- it must never fall back to the unscoped entry.
    return demo_owner if isinstance(demo_owner, str) else "<unresolved-demo-owner>"


def access_scope() -> Hashable:
    """Return what a group build's owner list depends on for the current caller.

    ``None`` for an unscoped request (every caller sees the same owners), the
    demo owner for a demo-scoped request, and -- only while owner access is
    enforced under ``disable_auth`` (#11087) -- ``("user", <identity>)``, with
    ``None`` as the identity for an anonymous request. The tuple can never
    equal a demo owner string, so the two scopes cannot collide.
    """

    demo = _demo_scope()
    if demo is not None:
        return demo

    from backend.auth import owner_access_enforced_under_disable_auth, request_identity

    if not owner_access_enforced_under_disable_auth():
        return None
    identity = request_identity()
    return ("user", identity.strip().lower() if isinstance(identity, str) and identity.strip() else None)


def group_portfolio_cache_key(slug: str, pricing_date: dt.date | None) -> CacheKey:
    """Build the cache key for a group portfolio, including the caller's scope."""

    return (slug, pricing_date.isoformat() if pricing_date else None, access_scope())


def cached_group_portfolio(
    slug: str,
    pricing_date: dt.date | None,
    build: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the built group portfolio for ``slug``, from cache when fresh."""

    return _GROUP_PORTFOLIO_CACHE.get_or_build(group_portfolio_cache_key(slug, pricing_date), build)


def invalidate_group_portfolios() -> None:
    """Drop every cached group portfolio, and the shared performance inputs.

    Deliberately coarse: a write to one owner changes the ``all`` group, every
    group that owner belongs to, and every ``as_of`` variant of each. Working
    out which entries survive costs more than rebuilding them. The performance
    inputs are built from the same account files and prices, so the same
    writes make them stale.
    """

    _GROUP_PORTFOLIO_CACHE.clear()
    invalidate_performance_inputs()


@contextmanager
def sharing_performance_inputs() -> Iterator[None]:
    """Let :func:`memoised` cache and share builds for the duration of the block."""

    token = _SHARING_PERFORMANCE_INPUTS.set(True)
    try:
        yield
    finally:
        _SHARING_PERFORMANCE_INPUTS.reset(token)


def memoised(key: CacheKey, build: Callable[[], _T]) -> _T:
    """Return ``build()``, shared across concurrent and recent callers inside :func:`sharing_performance_inputs`.

    Outside that block ``build`` simply runs. Inside it the result is cached
    for :data:`PERFORMANCE_INPUTS_TTL_SECONDS` under ``key`` plus the caller's
    scope (:func:`access_scope`) and the timeseries cache-only mode (both change what a build
    reads), and concurrent misses for one key run a single build. ``key`` must
    name every other input the build varies on.

    Any returned value is cached, ``None`` included ("this owner has no
    ledger" is a real answer); a build that fails must raise, which caches
    nothing. The cache is per process, so it shares work between requests
    served by one backend process -- the local API, or one warm Lambda
    container -- not across containers.
    """

    if not _SHARING_PERFORMANCE_INPUTS.get():
        return build()
    from backend.timeseries.cache import is_cache_only

    scoped_key = (*key, access_scope(), is_cache_only())
    return _PERFORMANCE_INPUTS_CACHE.get_or_build(scoped_key, build)


def invalidate_performance_inputs() -> None:
    """Drop every shared performance input."""

    _PERFORMANCE_INPUTS_CACHE.clear()


__all__ = [
    "GROUP_PORTFOLIO_TTL_SECONDS",
    "access_scope",
    "PERFORMANCE_INPUTS_TTL_SECONDS",
    "cached_group_portfolio",
    "group_portfolio_cache_key",
    "invalidate_group_portfolios",
    "invalidate_performance_inputs",
    "memoised",
    "sharing_performance_inputs",
]
