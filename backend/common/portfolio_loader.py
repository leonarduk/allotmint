"""
Return *all* portfolios (group + owner) with zero circular imports.
"""

from backend.common.group_portfolio import list_groups
from backend.common.portfolio import list_owners


def list_portfolios():
    portfolios = []

    # group portfolios (lazy import)
    for g in list_groups():
        slug = g["slug"] if isinstance(g, dict) else g
        from backend.common.group_portfolio import build_group_portfolio
        portfolios.append(build_group_portfolio(slug))

    # owner portfolios (lazy import)
    for owner in list_owners():
        from backend.common.portfolio import build_owner_portfolio
        portfolios.append(build_owner_portfolio(owner))

    return portfolios
