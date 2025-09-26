"""Endpoints exposing the unified Opportunities surface."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.agent import trading_agent
from backend.agent.models import TradingSignal
from backend.auth import decode_token
from backend.common import instrument_api
from backend.routes.portfolio import (
    _ALLOWED_DAYS as _PORTFOLIO_ALLOWED_DAYS,
    _calculate_weights_and_market_values,
    _enrich_movers_with_market_values,
)

router = APIRouter(tags=["opportunities"])

oauth2_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


class OpportunityEntry(BaseModel):
    """Mover row decorated with any matching trading signal."""

    ticker: str
    name: str
    change_pct: float
    last_price_gbp: Optional[float] = None
    last_price_date: Optional[str] = None
    market_value_gbp: Optional[float] = None
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
        mv_raw = summary.get("market_value_gbp")
        if mv_raw is None:
            continue
        mv = float(mv_raw)
        market_weight_totals[ticker] = mv
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
async def get_opportunities(
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

    context: OpportunitiesContext
    if has_group:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        user = decode_token(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        movers = _group_opportunities(group, days=days, limit=limit, min_weight=min_weight)
        context = OpportunitiesContext(source="group", group=group, days=days)
    else:
        parsed = [t.strip() for t in (tickers or "").split(",") if t.strip()]
        if not parsed:
            raise HTTPException(status_code=400, detail="No tickers provided")
        movers = instrument_api.top_movers(parsed, days, limit)
        context = OpportunitiesContext(source="watchlist", tickers=parsed, days=days)

    context.anomalies = list(movers.get("anomalies", []))

    raw_signals = trading_agent.run(notify=False)
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
                side=side,  # type: ignore[arg-type]
                signal=signal_map.get(ticker.upper()),
            )
            entries.append(entry)

    # Sort by absolute change so the most meaningful moves appear first.
    entries.sort(key=lambda e: abs(e.change_pct), reverse=True)

    return OpportunitiesResponse(entries=entries, signals=signals, context=context)
