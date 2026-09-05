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
demo scope in, and every caller must use it rather than assembling a key of
its own.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, Optional

from backend.common.ttl_cache import CacheKey, TTLCache

# Long enough to collapse the several calls a single page load makes, short
# enough that anything which changes the data without invalidating explicitly
# (an out-of-band edit to the account files, say) self-corrects in about a
# minute. Matches the TTL #7575 chose for /opportunities.
GROUP_PORTFOLIO_TTL_SECONDS = 60.0

_GROUP_PORTFOLIO_CACHE: TTLCache[Dict[str, Any]] = TTLCache(
    GROUP_PORTFOLIO_TTL_SECONDS,
    name="group_portfolio",
)


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


def group_portfolio_cache_key(slug: str, pricing_date: dt.date | None) -> CacheKey:
    """Build the cache key for a group portfolio, including the caller's scope."""

    return (slug, pricing_date.isoformat() if pricing_date else None, _demo_scope())


def cached_group_portfolio(
    slug: str,
    pricing_date: dt.date | None,
    build: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the built group portfolio for ``slug``, from cache when fresh."""

    return _GROUP_PORTFOLIO_CACHE.get_or_build(group_portfolio_cache_key(slug, pricing_date), build)


def invalidate_group_portfolios() -> None:
    """Drop every cached group portfolio.

    Deliberately coarse: a write to one owner changes the ``all`` group, every
    group that owner belongs to, and every ``as_of`` variant of each. Working
    out which entries survive costs more than rebuilding them.
    """

    _GROUP_PORTFOLIO_CACHE.clear()


__all__ = [
    "GROUP_PORTFOLIO_TTL_SECONDS",
    "cached_group_portfolio",
    "group_portfolio_cache_key",
    "invalidate_group_portfolios",
]
