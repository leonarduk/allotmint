"""
Owners / groups / portfolio endpoints (shared).

    - /owners
    - /groups
    - /portfolio/{owner}
    - /portfolio-group/{slug}
    - /portfolio-group/{slug}/instruments
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.common import (
    constants,
    data_loader,
    group_portfolio,
    instrument_api,
    portfolio_utils,
    prices,
    risk,
)
from backend.common import portfolio as portfolio_mod
from backend.config import config
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory
from backend.utils.pricing_dates import PricingDateCalculator

log = logging.getLogger("routes.portfolio")
router = APIRouter(tags=["portfolio"])
public_router = APIRouter(tags=["portfolio"])
oauth2_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
_ALLOWED_DAYS = {1, 7, 30, 90, 365}

KEY_TICKER = constants.TICKER
KEY_MARKET_VALUE_GBP = constants.MARKET_VALUE_GBP
KEY_GAINERS = "gainers"
KEY_LOSERS = "losers"


# ──────────────────────────────────────────────────────────────
# Pydantic models for validation
# ──────────────────────────────────────────────────────────────
class OwnerSummary(BaseModel):
    owner: str
    full_name: str
    accounts: List[str]
    has_transactions_artifact: bool = False


class GroupSummary(BaseModel):
    slug: str
    name: str
    members: List[str] = Field(default_factory=list)


class Mover(BaseModel):
    ticker: str
    name: str
    change_pct: float
    last_price_gbp: Optional[float] = None
    last_price_date: Optional[str] = None
    market_value_gbp: Optional[float] = None


class MoversResponse(BaseModel):
    gainers: List[Mover] = Field(default_factory=list)
    losers: List[Mover] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# Simple lists
# ──────────────────────────────────────────────────────────────
_CONVENTIONAL_ACCOUNT_EXTRAS = (
    "brokerage",
    "isa",
    "savings",
    "approvals",
    "settings",
)
_TRANSACTIONS_SUFFIX = "_transactions"
_DEFAULT_DEMO_OWNER: Dict[str, Any] = {
    "owner": "demo",
    "full_name": "Demo",
    "accounts": list(_CONVENTIONAL_ACCOUNT_EXTRAS),
    "has_transactions_artifact": False,
}


def _collect_account_stems(owner_dir: Optional[Path]) -> List[str]:
    """Return JSON account stems for ``owner_dir`` excluding metadata files."""

    if not owner_dir:
        return []

    stems: List[str] = []
    seen: set[str] = set()
    metadata_stems = {
        "person",
        "config",
        "notes",
        "settings",
        "approvals",
        "approval_requests",
    }

    try:
        entries = sorted(owner_dir.iterdir())
    except OSError:
        entries = []

    for path in entries:
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        stem = path.stem
        lowered = stem.casefold()
        if lowered in metadata_stems:
            continue
        if lowered.endswith(_TRANSACTIONS_SUFFIX):
            continue
        if lowered in seen:
            continue
        stems.append(stem)
        seen.add(lowered)

    return stems


def _has_transactions_artifact(owner_dir: Optional[Path], owner: str) -> bool:
    """Return ``True`` when ``owner_dir`` exposes a transactions export."""

    if not owner_dir:
        return False

    owner_slug = str(owner or "").strip()
    candidate_slugs: list[str] = []
    seen_slugs_cf: set[str] = set()
    if owner_slug:
        candidate_slugs.append(owner_slug)
        seen_slugs_cf.add(owner_slug.casefold())

    dir_name = owner_dir.name.strip() if owner_dir.name else ""
    dir_name_cf = dir_name.casefold() if dir_name else ""
    if dir_name and dir_name_cf not in seen_slugs_cf:
        candidate_slugs.append(dir_name)
        seen_slugs_cf.add(dir_name_cf)

    if not candidate_slugs:
        return False

    target_files = {f"{slug}{_TRANSACTIONS_SUFFIX}.json".casefold() for slug in candidate_slugs}
    target_dirs = {f"{slug}{_TRANSACTIONS_SUFFIX}".casefold() for slug in candidate_slugs}

    try:
        entries = list(owner_dir.iterdir())
    except OSError:
        entries = []

    for entry in entries:
        name_cf = entry.name.casefold()
        if name_cf in target_files and entry.is_file():
            return True
        if name_cf in target_dirs and entry.is_dir():
            return True

    return False


def _resolve_full_name(
    owner: str,
    entry: Dict[str, Any],
    meta: Optional[Dict[str, Any]],
) -> str:
    """Determine the preferred display name for ``owner``."""

    full_name = entry.get("full_name")
    if isinstance(full_name, str) and full_name.strip():
        return full_name.strip()

    meta = meta or {}
    if isinstance(meta, dict):
        for key in ("full_name", "display_name", "preferred_name", "owner", "name"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return owner


def _normalise_owner_entry(
    entry: Dict[str, Any],
    accounts_root: Path,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a cleaned owner summary enriched with conventional accounts."""

    owner = str(entry.get("owner", "")).strip()
    if not owner:
        return None

    owner_dir = resolve_owner_directory(accounts_root, owner)

    accounts: List[str] = []
    seen: set[str] = set()

    def _append(name: str) -> None:
        lowered = name.casefold()
        if lowered in seen:
            return
        accounts.append(name)
        seen.add(lowered)

    for source in (entry.get("accounts", []), _collect_account_stems(owner_dir)):
        if not isinstance(source, list):
            continue
        for candidate in source:
            if not isinstance(candidate, str):
                continue
            stripped = candidate.strip()
            if not stripped:
                continue
            _append(stripped)

    resolved_meta = meta
    if resolved_meta is None:
        try:
            resolved_meta = data_loader.load_person_meta(owner, accounts_root)
        except Exception:  # pragma: no cover - metadata lookup failures are tolerated
            resolved_meta = {}

    summary: Dict[str, Any] = {
        "owner": owner,
        "full_name": _resolve_full_name(owner, entry, resolved_meta),
        "accounts": accounts,
        "has_transactions_artifact": _has_transactions_artifact(owner_dir, owner),
    }

    return summary


def _build_demo_summary(accounts_root: Path) -> Dict[str, Any]:
    """Construct an owner summary for the demo account."""

    demo_dir = resolve_owner_directory(accounts_root, "demo")
    accounts = _collect_account_stems(demo_dir)
    try:
        meta = data_loader.load_person_meta("demo", accounts_root)
    except Exception:  # pragma: no cover - metadata lookup failures fall back to defaults
        meta = {}

    entry = {"owner": "demo", "accounts": accounts}
    summary = _normalise_owner_entry(entry, accounts_root, meta=meta)
    if summary:
        full_name = summary.get("full_name")
        if isinstance(full_name, str) and full_name.casefold() == "demo":
            summary["full_name"] = _DEFAULT_DEMO_OWNER["full_name"]
        summary["has_transactions_artifact"] = _has_transactions_artifact(demo_dir, "demo")
        return summary
    fallback = _DEFAULT_DEMO_OWNER.copy()
    fallback["has_transactions_artifact"] = _has_transactions_artifact(demo_dir, "demo")
    return fallback


def _list_owner_summaries(
    request: Request, current_user: Optional[str] = None
) -> List[OwnerSummary]:
    """Return owner summaries enriched with conventional account entries."""

    accounts_root = resolve_accounts_root(request, allow_missing=True)

    raw_entries = data_loader.list_plots(accounts_root, current_user)
    summaries: List[Dict[str, Any]] = []

    for entry in raw_entries:
        normalised = _normalise_owner_entry(entry, accounts_root)
        if normalised:
            summaries.append(normalised)

    demo_present = any(summary["owner"].casefold() == "demo" for summary in summaries)

    if summaries and not demo_present:
        summaries.append(_build_demo_summary(accounts_root))
    elif not summaries:
        summaries.append(_build_demo_summary(accounts_root))

    return [OwnerSummary(**summary) for summary in summaries]


if config.disable_auth:

    @router.get("/owners", response_model=List[OwnerSummary])
    async def owners(request: Request) -> List[OwnerSummary]:
        """List available owners including demo defaults when necessary."""

        return _list_owner_summaries(request)

else:

    @router.get("/owners", response_model=List[OwnerSummary])
    async def owners(
        request: Request, current_user: str = Depends(get_current_user)
    ) -> List[OwnerSummary]:
        """List available owners including demo defaults when necessary."""

        return _list_owner_summaries(request, current_user)
# =======
# @public_router.get("/owners", response_model=List[OwnerSummary])
# async def owners(request: Request, token: str | None = Depends(oauth2_optional)):
#     """List available owners and their accounts.

#     When the request is unauthenticated only the ``demo`` account is
#     exposed. If a valid JWT token is provided, the authenticated user's
#     full account list is returned.
#     """
#     username = decode_token(token) if token else None
#     if username:
#         current_user.set(username)
#     return data_loader.list_plots(request.app.state.accounts_root)


@router.get("/groups", response_model=List[GroupSummary])
async def groups():
    """
    Returns
        [
          {"slug": "children", "name": "Children", "members": ["alex", "joe"]},
          {"slug": "adults",   "name": "Adults",   "members": ["lucy", "steve"]},
          ...
        ]
    """
    return group_portfolio.list_groups()


# ──────────────────────────────────────────────────────────────
# Owner / group portfolios
# ──────────────────────────────────────────────────────────────
@router.get("/portfolio/{owner}")
async def portfolio(owner: str, request: Request):
    """Return the fully expanded portfolio for ``owner``.

    The helper function :func:`build_owner_portfolio` loads account data from
    disk, calculates current values and returns a nested structure describing
    the owner's holdings.
    """

    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    try:
        return portfolio_mod.build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/var/{owner}")
async def portfolio_var(owner: str, days: int = 365, confidence: float = 0.95, exclude_cash: bool = False):
    """Return historical-simulation VaR for ``owner``.

    Parameters
    ----------
    days:
        Length of the historical window used for returns. Must be positive.
        VaR is reported for 1-day and 10-day horizons.
    confidence:
        Quantile for losses in (0, 1) or, alternatively, a percentage in the
        range 0–100. Both ``0.95`` and ``95`` will request the 95 % quantile.
        Defaults to 0.95 (95 %); 0.99 is also common.
    exclude_cash:
        If ``True``, cash holdings are ignored when reconstructing the
        portfolio returns used for VaR.

    Returns a JSON object ``{"owner": owner, "as_of": <today>, "var": {...}}``.
    Raises 404 if the owner does not exist and 400 for invalid parameters.
    """

    if owner not in portfolio_mod.list_owners():
        raise HTTPException(status_code=404, detail="Owner not found")
    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence, include_cash=not exclude_cash)
        sharpe = risk.compute_sharpe_ratio(owner, days=days)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    calc = PricingDateCalculator()
    return {
        "owner": owner,
        "as_of": calc.reporting_date.isoformat(),
        "var": var,
        "sharpe_ratio": sharpe,
    }


@router.get("/var/{owner}/breakdown")
async def portfolio_var_breakdown(owner: str, days: int = 365, confidence: float = 0.95, exclude_cash: bool = False):
    """Return VaR totals with per-ticker contribution breakdown."""

    if owner not in portfolio_mod.list_owners():
        raise HTTPException(status_code=404, detail="Owner not found")
    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence, include_cash=not exclude_cash)
        breakdown = risk.compute_portfolio_var_breakdown(owner, days=days, confidence=confidence, include_cash=not exclude_cash)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    calc = PricingDateCalculator()
    return {
        "owner": owner,
        "as_of": calc.reporting_date.isoformat(),
        "var": var,
        "breakdown": breakdown,
    }


@router.post("/var/{owner}/recompute")
async def portfolio_var_recompute(owner: str, days: int = 365, confidence: float = 0.95):
    """Force recomputation of VaR for ``owner``.

    This endpoint mirrors :func:`portfolio_var` but is intended to be called
    when cached data is missing. It recalculates the metrics and returns the
    result without additional metadata.
    """

    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"owner": owner, "var": var}


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str):
    """Return the aggregated portfolio for a group.

    Groups are defined in configuration and simply reference a list of owner
    slugs. The aggregation combines holdings across all members.
    """

    try:
        return group_portfolio.build_group_portfolio(slug)
    except Exception as e:
        log.warning(f"Failed to load group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")


# ──────────────────────────────────────────────────────────────
# Group-level aggregation
# ──────────────────────────────────────────────────────────────
def _normalise_filter_values(values: Optional[Sequence[str]]) -> set[str] | None:
    """Lower-case and strip a query parameter list, dropping empty entries."""

    if values is None:
        return None

    if isinstance(values, str):
        values = [values]

    normalised = {
        str(value).strip().lower()
        for value in values
        if value is not None and str(value).strip()
    }
    return normalised or None


def _account_matches_filters(account: Dict[str, Any], filters: Dict[str, set[str]]) -> bool:
    """Return ``True`` when the account satisfies all provided filters."""

    for key, allowed_values in filters.items():
        value = account.get(key)
        if value is None:
            return False
        candidate = str(value).strip().lower()
        if candidate not in allowed_values:
            return False
    return True


@router.get("/portfolio-group/{slug}/instruments")
async def group_instruments(
    slug: str,
    owner: Optional[Sequence[str]] = Query(
        None,
        description="Filter holdings to accounts owned by the provided slug(s).",
    ),
    account_type: Optional[Sequence[str]] = Query(
        None,
        description="Filter holdings to specific account type(s).",
    ),
):
    """Return holdings for the group aggregated by ticker.

    Optional ``owner`` and ``account_type`` query parameters limit the accounts
    included in the aggregation. Provide the parameters multiple times to match
    more than one value.
    """

    try:
        gp = group_portfolio.build_group_portfolio(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc

    owner_filters = _normalise_filter_values(owner)
    account_type_filters = _normalise_filter_values(account_type)

    filters: Dict[str, set[str]] = {}
    if owner_filters:
        filters["owner"] = owner_filters
    if account_type_filters:
        filters["account_type"] = account_type_filters

    portfolio_for_aggregation: Dict[str, Any]
    if filters:
        filtered_accounts = [
            account
            for account in gp.get("accounts", [])
            if _account_matches_filters(account, filters)
        ]
        portfolio_for_aggregation = {**gp, "accounts": filtered_accounts}
    else:
        portfolio_for_aggregation = gp

    return portfolio_utils.aggregate_by_ticker(portfolio_for_aggregation)


@router.get("/portfolio-group/{slug}/sectors")
async def group_sectors(slug: str):
    """Return return contribution aggregated by sector."""
    try:
        gp = group_portfolio.build_group_portfolio(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    return portfolio_utils.aggregate_by_sector(gp)


@router.get("/portfolio-group/{slug}/regions")
async def group_regions(slug: str):
    """Return return contribution aggregated by region."""
    try:
        gp = group_portfolio.build_group_portfolio(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    return portfolio_utils.aggregate_by_region(gp)


def _calculate_weights_and_market_values(
    summaries: Sequence[Dict[str, Any]],
) -> Tuple[List[str], Dict[str, float], Dict[str, float]]:
    """Return tickers, equal-weight mapping and market values for summaries."""

    tickers: List[str] = []
    market_values: Dict[str, float] = {}
    for s in summaries:
        t = s.get("ticker")
        if not t:
            continue
        tickers.append(t)
        mv = s.get("market_value_gbp")
        if mv is not None:
            t_upper = t.upper()
            market_values[t_upper] = mv
            market_values[t_upper.split(".", 1)[0]] = mv

    n = len(tickers)
    if n == 0:
        return tickers, {}, market_values
    equal_weight = 100.0 / n
    weights = {t: equal_weight for t in tickers}
    return tickers, weights, market_values


def _enrich_movers_with_market_values(
    movers: Dict[str, List[Dict[str, Any]]],
    market_values: Dict[str, float],
) -> Dict[str, List[Dict[str, Any]]]:
    """Attach market values to mover rows."""

    for side in ("gainers", "losers"):
        for row in movers.get(side, []):
            mv = market_values.get(row["ticker"].upper())
            if mv is None:
                mv = market_values.get(row["ticker"].split(".")[0])
            row["market_value_gbp"] = mv
    return movers


@router.get(
    "/portfolio-group/{slug}/movers",
    response_model=MoversResponse,
    responses={
        200: {
            "description": (
                "Top gainers and losers for a group portfolio. "
                'Returns {"gainers": [], "losers": []} if the group holds no tickers.'
            )
        }
    },
)
async def group_movers(
    slug: str,
    days: int = Query(1, description="Lookback window"),
    limit: int = Query(10, description="Max results per side", le=100),
    min_weight: float = Query(0.0, description="Exclude positions below this percent"),
):
    """Return top gainers and losers for a group portfolio.

    If the group has no holdings, the endpoint returns ``{"gainers": [], "losers": []}``.
    """

    if days not in _ALLOWED_DAYS:
        raise HTTPException(status_code=400, detail="Invalid days")
    try:
        summaries = instrument_api.instrument_summaries_for_group(slug)
    except Exception as e:
        log.warning(f"Failed to load instrument summaries for group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")

    tickers, weight_map, market_values = _calculate_weights_and_market_values(summaries)
    total_mv = sum(float(s.get("market_value_gbp") or 0.0) for s in summaries)

    market_values = {}
    tickers = []
    weight_values = {}
    total_mv = 0.0
    for s in summaries:
        t = s.get(KEY_TICKER)
        if not t:
            continue
        tickers.append(t)
        mv = s.get(KEY_MARKET_VALUE_GBP)
        if mv is not None:
            t_upper = t.upper()
            market_values[t_upper] = mv
            market_values[t_upper.split(".")[0]] = mv
            weight_values[t] = mv
            total_mv += mv
            base = t.upper().split(".")[0]
            market_values[base] = mv

    if not tickers:
        return {KEY_GAINERS: [], KEY_LOSERS: []}

    # Compute weights in percent for filtering
    total_mv = sum(float(s.get("market_value_gbp") or 0.0) for s in summaries if s.get("ticker"))

    # Compute weights in percent proportional to each instrument's market value.
    # ``total_mv`` is the sum of all ``market_value_gbp`` values.

    if total_mv:
        weight_map = {t: mv / total_mv * 100.0 for t, mv in weight_values.items()}
    else:
        n = len(tickers)
        weight_map = {t: 100.0 / n for t in tickers}

    movers = instrument_api.top_movers(
        tickers,
        days,
        limit,
        min_weight=min_weight,
        weights=weight_map,
    )

    return _enrich_movers_with_market_values(movers, market_values)


@router.get("/account/{owner}/{account}")
async def get_account(owner: str, account: str, request: Request):
    root = resolve_accounts_root(request)

    try:
        data = data_loader.load_account(owner, account, root)
    except FileNotFoundError:
        search_root = root
        owner_dir = search_root / owner

        if not owner_dir.exists():
            fallback_paths = data_loader.resolve_paths(None, None)
            search_root = fallback_paths.accounts_root
            owner_dir = search_root / owner

        if not owner_dir.exists():
            raise HTTPException(status_code=404, detail="Account not found")

        match = next(
            (f.stem for f in owner_dir.glob("*.json") if f.stem.lower() == account.lower()),
            None,
        )
        if not match:
            raise HTTPException(status_code=404, detail="Account not found")
        data = data_loader.load_account(owner, match, search_root)
        account = match

    original_account_field = data.get("account")
    holdings = data.pop("holdings", data.pop("approvals", [])) or []
    account_type_value = data.get("account_type")

    data["holdings"] = holdings
    display_type: str | None = None
    if isinstance(account_type_value, str) and account_type_value.strip():
        display_type = account_type_value.strip()

    if display_type and display_type.lower() != account.lower() and original_account_field is None:
        data["account_display_type"] = display_type
        data["account_type"] = account
    else:
        data["account_type"] = display_type or account

    return data


@router.get("/portfolio-group/{slug}/instrument/{ticker}")
async def instrument_detail(slug: str, ticker: str):
    try:
        series = instrument_api.timeseries_for_ticker(ticker)
        prices_list = series.get("prices", [])
        positions_list = instrument_api.positions_for_ticker(slug, ticker)
    except Exception:
        raise HTTPException(status_code=404, detail="Instrument not found")

    if not prices_list and not positions_list:
        raise HTTPException(status_code=404, detail="Instrument not found")

    return {"prices": prices_list, "mini": series.get("mini", {}), "positions": positions_list}


@router.api_route("/prices/refresh", methods=["GET", "POST"])
async def refresh_prices():
    """Rebuild the in-memory price snapshot used by portfolio lookups."""

    log.info("Refreshing prices via /prices/refresh")
    result = prices.refresh_prices()
    return {"status": "ok", **result}
