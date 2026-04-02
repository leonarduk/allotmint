"""
Owners / groups / portfolio endpoints (shared).

    - /owners
    - /groups
    - /portfolio/{owner}
    - /portfolio-group/{slug}
    - /portfolio-group/{slug}/instruments
"""

from __future__ import annotations

import datetime as dt
import inspect
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.common.account_models import OwnerSummaryRecord, PersonMetadata
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
from backend.config import config, demo_identity
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


def _coerce_owner_summary_entry(entry: OwnerSummaryRecord | Dict[str, Any] | None) -> OwnerSummaryRecord:
    """Accept typed or legacy dict owner summaries for helper callers."""

    if isinstance(entry, OwnerSummaryRecord):
        return entry
    payload = dict(entry or {})
    return OwnerSummaryRecord.model_construct(
        owner=str(payload.get("owner", "")),
        accounts=list(payload.get("accounts", [])) if isinstance(payload.get("accounts", []), list) else [],
        full_name=payload.get("full_name").strip() if isinstance(payload.get("full_name"), str) and payload.get("full_name").strip() else None,
        email=payload.get("email").strip() if isinstance(payload.get("email"), str) and payload.get("email").strip() else None,
        has_transactions_artifact=bool(payload.get("has_transactions_artifact", False)),
    )


def _coerce_person_metadata(meta: PersonMetadata | Dict[str, Any] | None) -> PersonMetadata | None:
    """Accept typed or legacy dict metadata for helper callers."""

    if meta is None or isinstance(meta, PersonMetadata):
        return meta
    return PersonMetadata.model_validate(meta)


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------
def _resolve_pricing_date(as_of: str | None) -> dt.date | None:
    """Validate an ``as_of`` query parameter and return a pricing date."""

    if not as_of:
        return None

    try:
        candidate = dt.date.fromisoformat(as_of)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail="Invalid as_of date") from exc

    if candidate > dt.date.today():
        raise HTTPException(status_code=400, detail="Date cannot be in the future")

    calc = PricingDateCalculator()
    return calc.resolve_weekday(candidate, forward=False)


def _build_group_portfolio(slug: str, pricing_date: dt.date | None) -> Dict[str, Any]:
    """Return a group portfolio, tolerating simplified test doubles."""

    builder = group_portfolio.build_group_portfolio
    kwargs: Dict[str, Any] = {}

    try:
        params = inspect.signature(builder).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        params = {}

    if pricing_date is not None and "pricing_date" in params:
        kwargs["pricing_date"] = pricing_date

    return builder(slug, **kwargs)


# --------------------------------------------------------------
# Pydantic models for validation
# --------------------------------------------------------------
class OwnerSummary(BaseModel):
    owner: str
    full_name: str
    accounts: List[str]
    email: Optional[str] = None
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


# --------------------------------------------------------------
# Simple lists
# --------------------------------------------------------------
_CONVENTIONAL_ACCOUNT_EXTRAS = (
    "brokerage",
    "isa",
    "savings",
    "approvals",
    "settings",
)
_TRANSACTIONS_SUFFIX = "_transactions"


def _default_demo_owner(identity: str | None = None) -> Dict[str, Any]:
    """Return a template summary for the configured demo identity."""

    identity = identity or demo_identity()
    display_name = identity.replace("-", " ").strip() if identity else "Demo"
    if not display_name:
        display_name = "Demo"
    return {
        "owner": identity,
        "full_name": display_name.title(),
        "accounts": list(_CONVENTIONAL_ACCOUNT_EXTRAS),
        "has_transactions_artifact": False,
    }


def _collect_account_stems(owner_dir: Optional[Path]) -> List[str]:
    """Return JSON account stems for ``owner_dir`` excluding metadata files."""

    if not owner_dir:
        return []

    def _score_variant(value: str) -> tuple[int, str]:
        if value.islower():
            return (3, value)
        if any(ch.isupper() for ch in value):
            return (2, value)
        return (1, value)

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

    preferred: dict[str, str] = {}

    def _best_variant(stem: str, path: Path) -> str:
        candidate = stem
        score = _score_variant(candidate)

        try:
            resolved = path.resolve()
        except OSError:
            resolved = None
        else:
            if resolved.exists():
                resolved_stem = resolved.stem
                resolved_score = _score_variant(resolved_stem)
                if resolved_score > score:
                    candidate = resolved_stem
                    score = resolved_score
        return candidate.lower()

    for path in entries:
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        stem = path.stem
        lowered = stem.casefold()
        if lowered in metadata_stems:
            continue
        if lowered.endswith(_TRANSACTIONS_SUFFIX):
            continue

        candidate = _best_variant(stem, path)
        existing = preferred.get(lowered)
        if not existing or _score_variant(candidate) > _score_variant(existing):
            preferred[lowered] = candidate

    stems = sorted(
        preferred.values(),
        key=lambda name: (
            name.casefold(),
            -_score_variant(name)[0],
            name,
        ),
    )

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
    entry: OwnerSummaryRecord | Dict[str, Any] | None,
    meta: PersonMetadata | Dict[str, Any] | None,
) -> str:
    """Determine the preferred display name for ``owner``."""

    entry_record = _coerce_owner_summary_entry(entry)
    meta_record = _coerce_person_metadata(meta)

    if entry_record.full_name:
        return entry_record.full_name

    if meta_record:
        for value in (meta_record.full_name, meta_record.display_name, meta_record.preferred_name, meta_record.owner):
            if isinstance(value, str) and value.strip():
                return value.strip()

    return owner


def _normalise_owner_entry(
    entry: OwnerSummaryRecord | Dict[str, Any] | None,
    accounts_root: Path,
    *,
    meta: PersonMetadata | None = None,
    include_conventional_extras: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return a cleaned owner summary enriched with conventional accounts."""

    entry_record = _coerce_owner_summary_entry(entry)
    owner = entry_record.owner.strip()
    if not owner:
        return None

    owner_dir = resolve_owner_directory(accounts_root, owner)

    def _score_variant(value: str) -> tuple[int, str]:
        if value.isupper():
            return (3, value)
        if any(ch.isupper() for ch in value):
            return (2, value)
        return (1, value)

    accounts: List[str] = []
    seen: dict[str, int] = {}

    def _append(name: str, *, prefer_variant: bool) -> None:
        lowered = name.casefold()
        if lowered in seen:
            if not prefer_variant:
                return
            idx = seen[lowered]
            if _score_variant(name) > _score_variant(accounts[idx]):
                accounts[idx] = name
            return
        seen[lowered] = len(accounts)
        accounts.append(name)

    meta_provided = meta is not None

    sources = [
        (entry_record.accounts, False),
        (_collect_account_stems(owner_dir), True),
    ]

    for source, allow_variant in sources:
        if not isinstance(source, list):
            continue
        for candidate in source:
            if not isinstance(candidate, str):
                continue
            stripped = candidate.strip()
            if not stripped:
                continue
            _append(stripped, prefer_variant=allow_variant)

    if meta_provided and include_conventional_extras:
        for conventional in _CONVENTIONAL_ACCOUNT_EXTRAS:
            _append(conventional, prefer_variant=True)

    transactions_entry: Optional[str] = None
    if owner_dir:
        owner_slug = owner.strip()
        target = f"{owner_slug}{_TRANSACTIONS_SUFFIX}".casefold()
        try:
            for entry_path in owner_dir.iterdir():
                if entry_path.name.casefold() == target and entry_path.is_dir():
                    transactions_entry = entry_path.name
                    break
        except OSError:
            transactions_entry = None

    if transactions_entry:
        _append(transactions_entry, prefer_variant=True)

    resolved_meta = _coerce_person_metadata(meta)
    if resolved_meta is None:
        try:
            resolved_meta = _coerce_person_metadata(data_loader.load_person_metadata(owner, accounts_root))
        except Exception:  # pragma: no cover - metadata lookup failures are tolerated
            resolved_meta = PersonMetadata()

    summary: Dict[str, Any] = {
        "owner": owner,
        "full_name": _resolve_full_name(owner, entry, resolved_meta),
        "accounts": accounts,
    }

    artifact_present = _has_transactions_artifact(owner_dir, owner)
    if not meta_provided:
        summary["has_transactions_artifact"] = artifact_present

    if resolved_meta and resolved_meta.email:
        summary["email"] = resolved_meta.email.strip()

    return summary


def _resolve_demo_owner(accounts_root: Path) -> tuple[str, Path | None]:
    """Return the preferred demo identity and resolved directory."""

    for identity in data_loader.demo_identity_aliases():
        owner_dir = resolve_owner_directory(accounts_root, identity)
        if owner_dir:
            return identity, owner_dir
    identity = demo_identity()
    return identity, resolve_owner_directory(accounts_root, identity)


def _build_demo_summary(accounts_root: Path) -> Dict[str, Any]:
    """Construct an owner summary for the configured demo account."""

    identity, demo_dir = _resolve_demo_owner(accounts_root)
    accounts = _collect_account_stems(demo_dir)
    try:
        meta = data_loader.load_person_metadata(identity, accounts_root)
    except Exception:  # pragma: no cover - metadata lookup failures fall back to defaults
        meta = PersonMetadata()

    entry = OwnerSummaryRecord(owner=identity, accounts=accounts)
    summary = _normalise_owner_entry(
        entry,
        accounts_root,
        meta=meta,
        include_conventional_extras=False,
    )
    if summary:
        full_name = summary.get("full_name")
        if isinstance(full_name, str) and full_name.casefold() == identity.casefold():
            summary["full_name"] = _default_demo_owner(identity)["full_name"]
        summary["has_transactions_artifact"] = _has_transactions_artifact(demo_dir, identity)
        return summary
    fallback = _default_demo_owner(identity).copy()
    fallback["has_transactions_artifact"] = _has_transactions_artifact(demo_dir, identity)
    return fallback


def _list_owner_summaries(
    request: Request, current_user: Optional[str] = None
) -> List[OwnerSummary]:
    """Return owner summaries enriched with conventional account entries."""

    accounts_root = resolve_accounts_root(request, allow_missing=True)

    raw_entries = [
        OwnerSummaryRecord.model_validate(entry)
        for entry in data_loader.list_plots(accounts_root, current_user)
    ]
    summaries: List[Dict[str, Any]] = []

    for entry in raw_entries:
        normalised = _normalise_owner_entry(entry, accounts_root)
        if normalised:
            summaries.append(normalised)

    identity = demo_identity()

    def _append_demo_summary() -> None:
        summaries.append(_build_demo_summary(accounts_root))

    if not summaries:
        _append_demo_summary()

    demo_aliases = {alias.lower() for alias in data_loader.demo_identity_aliases()}
    known = {summary["owner"].lower() for summary in summaries}
    if not known.intersection(demo_aliases):
        _append_demo_summary()

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


@router.get("/groups", response_model=List[GroupSummary])
async def groups():
    return group_portfolio.list_groups()


# --------------------------------------------------------------
# Owner / group portfolios
# --------------------------------------------------------------
@router.get("/portfolio/{owner}")
async def portfolio(owner: str, request: Request, as_of: str | None = None):
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    pricing_date = _resolve_pricing_date(as_of)

    try:
        return portfolio_mod.build_owner_portfolio(
            owner, accounts_root, pricing_date=pricing_date
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")


@router.get("/portfolio/{owner}/sectors")
async def portfolio_sectors(owner: str, request: Request, as_of: str | None = None):
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    pricing_date = _resolve_pricing_date(as_of)

    try:
        portfolio_data = portfolio_mod.build_owner_portfolio(
            owner, accounts_root, pricing_date=pricing_date
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")

    return portfolio_utils.aggregate_by_sector(portfolio_data)


@router.get("/var/{owner}")
async def portfolio_var(
    owner: str,
    request: Request,
    days: int = 365,
    confidence: float = 0.95,
    exclude_cash: bool = False,
):
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
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
async def portfolio_var_breakdown(
    owner: str,
    request: Request,
    days: int = 365,
    confidence: float = 0.95,
    exclude_cash: bool = False,
    horizon_days: int = 1,
):
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence, include_cash=not exclude_cash)
        scenario_payload = risk.compute_portfolio_var_scenarios(
            owner,
            days=days,
            confidence=confidence,
            horizon_days=horizon_days,
            include_cash=not exclude_cash,
        )
        breakdown = risk.compute_portfolio_var_breakdown(
            owner,
            days=days,
            confidence=confidence,
            include_cash=not exclude_cash,
            scenario_date=scenario_payload.get("var_date"),
            horizon_days=horizon_days,
        )
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
        "scenarios": scenario_payload.get("scenarios", []),
        "var_date": scenario_payload.get("var_date"),
        "var_loss_percent": scenario_payload.get("var_loss_percent"),
    }


@router.post("/var/{owner}/recompute")
async def portfolio_var_recompute(
    owner: str,
    request: Request,
    days: int = 365,
    confidence: float = 0.95,
):
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    try:
        var = risk.compute_portfolio_var(owner, days=days, confidence=confidence)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"owner": owner, "var": var}


@router.get("/portfolio-group/{slug}")
async def portfolio_group(slug: str, as_of: str | None = None):
    try:
        pricing_date = _resolve_pricing_date(as_of)
        return _build_group_portfolio(slug, pricing_date)
    except Exception as e:
        log.warning(f"Failed to load group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")


# --------------------------------------------------------------
# Group-level aggregation
# --------------------------------------------------------------
def _normalise_filter_values(values: Optional[Sequence[str]]) -> set[str] | None:
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
    as_of: str | None = None,
):
    try:
        pricing_date = _resolve_pricing_date(as_of)
        builder = group_portfolio.build_group_portfolio
        try:
            params = inspect.signature(builder).parameters
        except (TypeError, ValueError):  # pragma: no cover - non-standard callables
            params = {}

        if "pricing_date" in params:
            gp = builder(slug, pricing_date=pricing_date)
        else:
            gp = builder(slug)
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
async def group_sectors(slug: str, as_of: str | None = None):
    try:
        pricing_date = _resolve_pricing_date(as_of)
        gp = _build_group_portfolio(slug, pricing_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    return portfolio_utils.aggregate_by_sector(gp)


@router.get("/portfolio-group/{slug}/regions")
async def group_regions(slug: str, as_of: str | None = None):
    try:
        pricing_date = _resolve_pricing_date(as_of)
        gp = _build_group_portfolio(slug, pricing_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    return portfolio_utils.aggregate_by_region(gp)


def _calculate_weights_and_market_values(
    summaries: Sequence[Dict[str, Any]],
) -> Tuple[List[str], Dict[str, float], Dict[str, float]]:
    tickers: List[str] = []
    seen_tickers_upper: set[str] = set()
    market_values: Dict[str, float] = {}
    bare_alias_source: Dict[str, str] = {}
    for s in summaries:
        t = s.get("ticker")
        if not t:
            continue
        ticker = str(t).strip()
        if not ticker:
            continue
        ticker_upper = ticker.upper()
        if ticker_upper not in seen_tickers_upper:
            tickers.append(ticker_upper)
            seen_tickers_upper.add(ticker_upper)
        mv = s.get("market_value_gbp")
        if mv is not None:
            mv_float = float(mv)
            bare = ticker_upper.split(".", 1)[0]
            market_values[ticker_upper] = market_values.get(ticker_upper, 0.0) + mv_float
            if bare != ticker_upper:
                alias_source = bare_alias_source.get(bare)
                if alias_source in (None, ticker_upper):
                    bare_alias_source[bare] = ticker_upper
                    market_values[bare] = market_values[ticker_upper]

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
)
async def group_movers(
    slug: str,
    days: int = Query(1, description="Lookback window"),
    limit: int = Query(10, description="Max results per side", le=100),
    min_weight: float = Query(0.0, description="Exclude positions below this percent"),
):
    if days not in _ALLOWED_DAYS:
        raise HTTPException(status_code=400, detail="Invalid days")
    try:
        summaries = instrument_api.instrument_summaries_for_group(slug)
    except Exception as e:
        log.warning(f"Failed to load instrument summaries for group {slug}: {e}")
        raise HTTPException(status_code=404, detail="Group not found")

    tickers, weight_map, market_values = _calculate_weights_and_market_values(summaries)
    total_mv = sum(float(s.get("market_value_gbp") or 0.0) for s in summaries)

    if not tickers:
        return {KEY_GAINERS: [], KEY_LOSERS: []}

    if total_mv:
        weight_map = {t: (market_values.get(t.upper(), 0.0) / total_mv * 100.0) for t in tickers}

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
    except data_loader.ProviderUnavailable as exc:
        log.warning(
            "portfolio.account_provider_unavailable",
            extra={"event": "portfolio.account_provider_unavailable", "owner": owner, "account": account},
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
    except data_loader.InvalidPayload as exc:
        log.warning(
            "portfolio.account_invalid_payload",
            extra={"event": "portfolio.account_invalid_payload", "owner": owner, "account": account},
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail="Account data payload is invalid") from exc
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
        try:
            data = data_loader.load_account(owner, match, search_root)
        except data_loader.ProviderUnavailable as exc:
            raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
        except data_loader.InvalidPayload as exc:
            raise HTTPException(status_code=502, detail="Account data payload is invalid") from exc
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
    log.info("Refreshing prices via /prices/refresh")
    result = prices.refresh_prices()
    return {"status": "ok", **result}
