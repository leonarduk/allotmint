"""Endpoints exposing the unified Opportunities surface."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.agent import trading_agent
from backend.agent.models import TradingSignal
from backend.auth import decode_token, is_demo_request
from backend.common import instrument_api
from backend.common.ttl_cache import TTLCache
from backend.config import config
from backend.routes.portfolio import _ALLOWED_DAYS as _PORTFOLIO_ALLOWED_DAYS
from backend.routes.portfolio import (
    _calculate_weights_and_market_values,
    _enrich_movers_with_market_values,
)

router = APIRouter(tags=["opportunities"])

oauth2_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Signal generation (trading_agent.run) loads 60 days of history per ticker on
# every call -- see the comment further down where it's invoked. Without this
# cache, every Opportunities page view/refresh (including repeat views of the
# public "buffett" demo account) re-runs that full computation from scratch.
# A short TTL keeps repeat views fast while staying well under any interval a
# real trade or price move would need to show up within.
#
# The dict/lock/staleness machinery this used to hold inline now lives in
# TTLCache (#7581), which deep-copies on both store and read exactly as the
# `model_copy(deep=True)` calls here used to.
_OPPORTUNITIES_CACHE_TTL_SECONDS = 60.0
_OpportunitiesCacheKey = Tuple[object, ...]
_OPPORTUNITIES_CACHE: TTLCache["OpportunitiesResponse"] = TTLCache(
    _OPPORTUNITIES_CACHE_TTL_SECONDS,
    name="opportunities",
)


def _cached_opportunities_response(key: _OpportunitiesCacheKey, build) -> "OpportunitiesResponse":
    """Return a cached response for ``key`` if still fresh, else build and cache one."""

    return _OPPORTUNITIES_CACHE.get_or_build(key, build)


class OpportunityEntry(BaseModel):
    """Mover row decorated with any matching trading signal."""

    ticker: str
    name: str
    change_pct: float
    last_price_gbp: Optional[float] = None
    last_price_date: Optional[str] = None
    market_value_gbp: Optional[float] = None
    instrument_type: Optional[str] = None
    side: Literal["gainers", "losers"]
    signal: Optional[TradingSignal] = None


class OpportunitiesContext(BaseModel):
    """Metadata describing the request that produced the entries."""

    source: Literal["group", "watchlist"]
    group: Optional[str] = None
    tickers: List[str] = Field(default_factory=list)
    days: int
    anomalies: List[str] = Field(default_factory=list)


class OpportunitiesResponse(BaseModel):
    entries: List[OpportunityEntry] = Field(default_factory=list)
    signals: List[TradingSignal] = Field(default_factory=list)
    context: OpportunitiesContext


def _group_opportunities(
    slug: str,
    *,
    days: int,
    limit: int,
    min_weight: float,
) -> Dict[str, List[Dict[str, object]]]:
    """Return movers for a portfolio group enriched with market values."""

    try:
        summaries = instrument_api.instrument_summaries_for_group(slug)
    except Exception as exc:  # pragma: no cover - defensive logging handled upstream
        raise HTTPException(status_code=404, detail="Group not found") from exc

    tickers, weight_map, market_values = _calculate_weights_and_market_values(summaries)
    if not tickers:
        return {"gainers": [], "losers": [], "anomalies": []}

    # ``_calculate_weights_and_market_values`` returns equal weights. When we
    # have market values we can produce proportional weights so the
    # ``min_weight`` filter behaves like the existing group movers endpoint.
    market_weight_totals: Dict[str, float] = {}
    total_mv = 0.0
    for summary in summaries:
        ticker = summary.get("ticker")
        if not ticker:
            continue
        ticker_key = str(ticker).strip().upper()
        if not ticker_key:
            continue
        mv_raw = summary.get("market_value_gbp")
        if mv_raw is None:
            continue
        mv = float(mv_raw)
        market_weight_totals[ticker_key] = market_weight_totals.get(ticker_key, 0.0) + mv
        total_mv += mv

    if total_mv > 0:
        weight_map = {t: mv / total_mv * 100.0 for t, mv in market_weight_totals.items()}

    movers = instrument_api.top_movers(
        tickers,
        days,
        limit,
        min_weight=min_weight,
        weights=weight_map,
    )
    return _enrich_movers_with_market_values(movers, market_values)


@router.get("/opportunities", response_model=OpportunitiesResponse)
def get_opportunities(
    *,
    group: Optional[str] = Query(None, description="Portfolio group slug"),
    tickers: Optional[str] = Query(None, description="Comma separated tickers"),
    days: int = Query(1, description="Lookback window"),
    limit: int = Query(10, description="Maximum results per side", le=100),
    min_weight: float = Query(0.0, description="Exclude positions below this percent"),
    token: Optional[str] = Depends(oauth2_optional),
) -> OpportunitiesResponse:
    """Return movers decorated with trading signals for the Opportunities view."""

    if days not in _PORTFOLIO_ALLOWED_DAYS:
        raise HTTPException(status_code=400, detail="Invalid days")

    has_group = bool(group)
    has_tickers = bool(tickers)
    if has_group == has_tickers:
        raise HTTPException(
            status_code=400,
            detail="Specify either a group or tickers, but not both",
        )

    cache_key: _OpportunitiesCacheKey
    if has_group:
        # A demo-scoped token is already authorized at this point --
        # backend.bootstrap.middleware.demo_scope_gate resolves it
        # unconditionally, for every request, before this handler ever runs.
        # decode_token() below is the ordinary backend-JWT decoder and
        # deliberately returns None for a demo token (backend/auth.py:255-256)
        # so it can never be mistaken for a real login; check is_demo_request()
        # first, exactly as ensure_owner_access does, or a demo token here
        # falls straight into the "not user" 401 instead (found live: it broke
        # the Movers page for the buffett demo account, since "Portfolio"
        # watchlist routes through GET /opportunities?group=...).
        if is_demo_request():
            pass
        elif token:
            user = decode_token(token)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                )
        elif not config.disable_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        cache_key = ("group", group, days, limit, min_weight)

        def _build() -> OpportunitiesResponse:
            movers = _group_opportunities(group, days=days, limit=limit, min_weight=min_weight)
            context = OpportunitiesContext(source="group", group=group, days=days)
            return _build_opportunities_response(movers, context)

    else:
        parsed = [t.strip() for t in (tickers or "").split(",") if t.strip()]
        if not parsed:
            raise HTTPException(status_code=400, detail="No tickers provided")
        cache_key = ("watchlist", tuple(sorted(parsed)), days, limit)

        def _build() -> OpportunitiesResponse:
            movers = instrument_api.top_movers(parsed, days, limit)
            context = OpportunitiesContext(source="watchlist", tickers=parsed, days=days)
            return _build_opportunities_response(movers, context)

    return _cached_opportunities_response(cache_key, _build)


def _build_opportunities_response(
    movers: Dict[str, List[Dict[str, object]]],
    context: OpportunitiesContext,
) -> OpportunitiesResponse:
    context.anomalies = list(movers.get("anomalies", []))

    # Signal generation loads 60 days of history for every requested ticker.
    # Restrict it to the bounded mover result rather than re-analysing the
    # entire portfolio universe on every Opportunities page refresh.
    mover_tickers = {
        str(row.get("ticker") or "").strip() for side in ("gainers", "losers") for row in movers.get(side, [])
    }
    mover_tickers.discard("")
    raw_signals = trading_agent.run(sorted(mover_tickers), notify=False) if mover_tickers else []
    signals = [TradingSignal.model_validate(sig) for sig in raw_signals]
    signal_map = {sig.ticker.upper(): sig for sig in signals}

    entries: List[OpportunityEntry] = []
    for side in ("gainers", "losers"):
        for row in movers.get(side, []):
            ticker = str(row.get("ticker") or "").strip()
            if not ticker:
                continue
            name = str(row.get("name") or ticker)
            change = float(row.get("change_pct") or 0.0)
            entry = OpportunityEntry(
                ticker=ticker,
                name=name,
                change_pct=change,
                last_price_gbp=row.get("last_price_gbp"),
                last_price_date=row.get("last_price_date"),
                market_value_gbp=row.get("market_value_gbp"),
                instrument_type=row.get("instrument_type"),
                side=side,  # type: ignore[arg-type]
                signal=signal_map.get(ticker.upper()),
            )
            entries.append(entry)

    # Sort by absolute change so the most meaningful moves appear first.
    entries.sort(key=lambda e: abs(e.change_pct), reverse=True)

    return OpportunitiesResponse(entries=entries, signals=signals, context=context)
