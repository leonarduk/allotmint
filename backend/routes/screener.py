from __future__ import annotations

"""API route for basic stock screening based on valuation metrics."""

import hashlib
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from backend.common import instrument_api
from backend.common.core_optional import missing_package, require_core
from backend.common.instruments import get_instrument_meta
from backend.common.prices import get_security_meta
from backend.logging_setup import sanitise_log_value
from backend.utils import page_cache

try:
    from backend.screener import screen
except ModuleNotFoundError:
    screen = None

# Imported on its own so an older allotmint-pro without the valuation module
# (allotmint-pro#259) still serves /screener; only /screener/valuation is gated.
try:
    from allotmint_pro.screener.valuation import instrument_valuation
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    instrument_valuation = None

# Likewise for the technicals module (allotmint-pro: instrument technicals).
try:
    from allotmint_pro.screener.technicals import instrument_technicals
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    instrument_technicals = None

# Likewise for the per-company credit-risk verdict (allotmint-pro#701).
try:
    from allotmint_pro.mcp_server.credit_risk_tools import get_credit_risk
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    get_credit_risk = None

# The pro tool reports bad input as mcp's ToolError. Guarded on its own so a
# missing mcp install never takes the other screener routes down with it.
try:
    from mcp.server.mcpserver.exceptions import ToolError
except ModuleNotFoundError as exc:
    if not missing_package(exc, "mcp"):
        raise

    class ToolError(Exception):  # type: ignore[no-redef]
        """Never raised: without mcp the pro tool cannot be installed either."""


logger = logging.getLogger(__name__)


class RankedFundamentals(BaseModel):
    """Stable public response contract for ranked screener results.

    Keep this API-facing model independent from the optional implementation
    package so free-tier deployments publish the same OpenAPI schema.

    MAINTENANCE: the field list below is a manually-synced snapshot of
    ``allotmint_pro.screener.Fundamentals`` (a private-repo model this
    module cannot import from directly, see backend/screener/__init__.py).
    FastAPI's response_model filtering silently drops any field a route
    returns that isn't declared here -- so if the private model ever gains
    a field, paid-tier ``/screener`` responses will silently lose it from
    the API response until this list is updated to match.
    ``tests/routes/test_screener_schema.py::test_ranked_fundamentals_matches_allotmint_pro_fundamentals``
    guards against this drift by introspection whenever ``allotmint_pro`` is
    installed (skips cleanly otherwise); see allotmint#6833.
    """

    ticker: str
    name: str | None = None
    # Provenance: the provider that supplied the values ("yahoo",
    # "alpha_vantage") and the ISO date they were fetched. Kept as plain str
    # so this schema stays independent of allotmint_pro's Literal type.
    source: str | None = None
    as_of: str | None = None
    peg_ratio: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    de_ratio: float | None = None
    lt_de_ratio: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    fcf: float | None = None
    eps: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    ebitda_margin: float | None = None
    roa: float | None = None
    roe: float | None = None
    roi: float | None = None
    dividend_yield: float | None = None
    dividend_payout_ratio: float | None = None
    beta: float | None = None
    shares_outstanding: int | None = None
    float_shares: int | None = None
    market_cap: int | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    avg_volume: int | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None
    book_value: float | None = None
    book_value_as_of: str | None = None
    total_debt: int | None = None
    total_cash: int | None = None
    net_debt: int | None = None
    price: float | None = None
    currency: str | None = None
    financial_currency: str | None = None
    revenue: int | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    rank: int
    # Route-only: not present on allotmint_pro.screener.Fundamentals.
    # Populated here (not by the screener engine) from portfolio holdings
    # metadata after screen() returns -- see allotmint#6876 and
    # _ROUTE_ONLY_FIELDS in tests/routes/test_screener_schema.py.
    instrument_type: str | None = None
    # Route-only, like instrument_type: read from instrument metadata so the
    # Screener can show it on hover over the ticker.
    sector: str | None = None


router = APIRouter(prefix="/screener", tags=["screener"])

SCREENER_TTL = 900  # seconds


def _hash_params(
    symbols: List[str],
    peg_max: float | None,
    pe_max: float | None,
    de_max: float | None,
    lt_de_max: float | None,
    interest_coverage_min: float | None,
    current_ratio_min: float | None,
    quick_ratio_min: float | None,
    fcf_min: float | None,
    eps_min: float | None,
    gross_margin_min: float | None,
    operating_margin_min: float | None,
    net_margin_min: float | None,
    ebitda_margin_min: float | None,
    roa_min: float | None,
    roe_min: float | None,
    roi_min: float | None,
    dividend_yield_min: float | None,
    dividend_payout_ratio_max: float | None,
    beta_max: float | None,
    shares_outstanding_min: int | None,
    float_shares_min: int | None,
    market_cap_min: int | None,
    high_52w_max: float | None,
    low_52w_min: float | None,
    avg_volume_min: int | None,
    pb_max: float | None,
    ps_max: float | None,
    ev_ebitda_max: float | None,
    revenue_growth_min: float | None,
    earnings_growth_min: float | None,
):
    params = "|".join(
        [
            ",".join(symbols),
            str(peg_max),
            str(pe_max),
            str(de_max),
            str(fcf_min),
            str(eps_min),
            str(fcf_min),
            str(gross_margin_min),
            str(operating_margin_min),
            str(net_margin_min),
            str(ebitda_margin_min),
            str(roa_min),
            str(roe_min),
            str(roi_min),
            str(lt_de_max),
            str(interest_coverage_min),
            str(current_ratio_min),
            str(quick_ratio_min),
            str(fcf_min),
            str(dividend_yield_min),
            str(dividend_payout_ratio_max),
            str(beta_max),
            str(shares_outstanding_min),
            str(float_shares_min),
            str(market_cap_min),
            str(high_52w_max),
            str(low_52w_min),
            str(avg_volume_min),
            str(pb_max),
            str(ps_max),
            str(ev_ebitda_max),
            str(revenue_growth_min),
            str(earnings_growth_min),
        ]
    )
    page = "screener_" + hashlib.sha1(params.encode()).hexdigest()

    def _call():
        rows = [
            r.model_dump()
            for r in screen(
                symbols,
                peg_max=peg_max,
                pe_max=pe_max,
                de_max=de_max,
                lt_de_max=lt_de_max,
                interest_coverage_min=interest_coverage_min,
                current_ratio_min=current_ratio_min,
                quick_ratio_min=quick_ratio_min,
                fcf_min=fcf_min,
                eps_min=eps_min,
                gross_margin_min=gross_margin_min,
                operating_margin_min=operating_margin_min,
                net_margin_min=net_margin_min,
                ebitda_margin_min=ebitda_margin_min,
                roa_min=roa_min,
                roe_min=roe_min,
                roi_min=roi_min,
                dividend_yield_min=dividend_yield_min,
                dividend_payout_ratio_max=dividend_payout_ratio_max,
                beta_max=beta_max,
                shares_outstanding_min=shares_outstanding_min,
                float_shares_min=float_shares_min,
                market_cap_min=market_cap_min,
                high_52w_max=high_52w_max,
                low_52w_min=low_52w_min,
                avg_volume_min=avg_volume_min,
                pb_max=pb_max,
                ps_max=ps_max,
                ev_ebitda_max=ev_ebitda_max,
                revenue_growth_min=revenue_growth_min,
                earnings_growth_min=earnings_growth_min,
            )
        ]
        _apply_instrument_type(rows)
        _apply_instrument_meta(rows)
        return rows

    return page, _call


def _apply_instrument_type(rows: List[dict]) -> None:
    """Populate ``instrument_type`` from portfolio holdings metadata.

    The screener engine (``allotmint_pro.screener.Fundamentals``) has no
    concept of instrument type, so this route-only field is filled in here
    after ``screen()`` returns rather than by the engine -- see
    allotmint#6876.
    """
    for row in rows:
        meta = get_security_meta(row["ticker"]) or {}
        row["instrument_type"] = meta.get("instrument_type")


def _apply_instrument_meta(rows: List[dict]) -> None:
    """Populate ``sector`` (and a missing ``name``) from instrument metadata.

    Reads the stored instrument file only -- ``get_instrument_meta`` never
    makes a live provider call -- so a ticker with no file keeps ``None``.
    """
    for row in rows:
        meta = get_instrument_meta(row["ticker"])
        row["sector"] = meta.get("sector") or None
        if not row.get("name") and meta.get("name"):
            row["name"] = meta["name"]


def _apply_rank(rows: List[dict]) -> None:
    rows.sort(
        key=lambda x: (
            float("inf") if x.get("peg_ratio") in (None,) or x.get("roe") in (None, 0) else x["peg_ratio"] / x["roe"]
        )
    )
    for i, row in enumerate(rows, 1):
        row["rank"] = i


@router.get("/", response_model=List[RankedFundamentals])
def screener(
    background_tasks: BackgroundTasks,
    tickers: str = Query(..., description="Comma-separated list of tickers"),
    peg_max: float | None = Query(None),
    pe_max: float | None = Query(None),
    de_max: float | None = Query(None),
    lt_de_max: float | None = Query(None),
    interest_coverage_min: float | None = Query(None),
    current_ratio_min: float | None = Query(None),
    quick_ratio_min: float | None = Query(None),
    fcf_min: float | None = Query(None),
    eps_min: float | None = Query(None),
    gross_margin_min: float | None = Query(None),
    operating_margin_min: float | None = Query(None),
    net_margin_min: float | None = Query(None),
    ebitda_margin_min: float | None = Query(None),
    roa_min: float | None = Query(None),
    roe_min: float | None = Query(None),
    roi_min: float | None = Query(None),
    dividend_yield_min: float | None = Query(None),
    dividend_payout_ratio_max: float | None = Query(None),
    beta_max: float | None = Query(None),
    shares_outstanding_min: int | None = Query(None),
    float_shares_min: int | None = Query(None),
    market_cap_min: int | None = Query(None),
    high_52w_max: float | None = Query(None),
    low_52w_min: float | None = Query(None),
    avg_volume_min: int | None = Query(None),
    pb_max: float | None = Query(None),
    ps_max: float | None = Query(None),
    ev_ebitda_max: float | None = Query(None),
    revenue_growth_min: float | None = Query(None, description="Fraction, e.g. 0.1 for 10%"),
    earnings_growth_min: float | None = Query(None, description="Fraction, e.g. 0.1 for 10%"),
):
    """Return tickers that meet the supplied screening criteria."""

    require_core(screen, "Screener")

    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers supplied")

    page, call = _hash_params(
        symbols,
        peg_max=peg_max,
        pe_max=pe_max,
        de_max=de_max,
        lt_de_max=lt_de_max,
        interest_coverage_min=interest_coverage_min,
        current_ratio_min=current_ratio_min,
        quick_ratio_min=quick_ratio_min,
        fcf_min=fcf_min,
        eps_min=eps_min,
        gross_margin_min=gross_margin_min,
        operating_margin_min=operating_margin_min,
        net_margin_min=net_margin_min,
        ebitda_margin_min=ebitda_margin_min,
        roa_min=roa_min,
        roe_min=roe_min,
        roi_min=roi_min,
        dividend_yield_min=dividend_yield_min,
        dividend_payout_ratio_max=dividend_payout_ratio_max,
        beta_max=beta_max,
        shares_outstanding_min=shares_outstanding_min,
        float_shares_min=float_shares_min,
        market_cap_min=market_cap_min,
        high_52w_max=high_52w_max,
        low_52w_min=low_52w_min,
        avg_volume_min=avg_volume_min,
        pb_max=pb_max,
        ps_max=ps_max,
        ev_ebitda_max=ev_ebitda_max,
        revenue_growth_min=revenue_growth_min,
        earnings_growth_min=earnings_growth_min,
    )

    page_cache.schedule_refresh(page, SCREENER_TTL, call)
    if not page_cache.is_stale(page, SCREENER_TTL):
        cached = page_cache.load_cache(page)
        if cached is not None:
            _apply_rank(cached)
            return cached

    try:
        payload = call()
        _apply_rank(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    background_tasks.add_task(page_cache.save_cache, page, payload)
    return payload


def _price_snapshot_flags(ticker: str) -> Dict[str, Any]:
    """The app's own staleness flag for ``ticker``'s latest price (the one holdings use)."""

    try:
        snap = instrument_api._price_and_changes(ticker)
    except Exception as exc:  # noqa: BLE001 -- the flag is advisory; never fail the profile over it
        logger.warning(
            "valuation: price snapshot lookup failed for %s: %s",
            sanitise_log_value(ticker),
            sanitise_log_value(exc),
        )
        return {"is_stale": None, "last_price_date": None}
    return {"is_stale": snap.get("is_stale"), "last_price_date": snap.get("last_price_date")}


@router.get("/valuation")
def valuation(ticker: str = Query(..., description="Full ticker, e.g. UKW.L")) -> Dict[str, Any]:
    """Valuation profile for one instrument (allotmint-pro#259).

    Multiples, NAV and premium/discount, income, gearing, a benchmark
    reference and risk, with data-quality flags. ``data_quality.price_snapshot``
    adds the app's own ``is_stale`` flag for the latest price so the page can
    show it next to the numbers. Positions' ``cost_basis_source`` flags are
    already on the ``/instrument`` payload the page holds.
    """

    require_core(instrument_valuation, "Instrument valuation")

    symbol = ticker.strip().upper()
    if not symbol or symbol.startswith("."):
        raise HTTPException(status_code=400, detail="No ticker supplied")
    try:
        profile = instrument_valuation(symbol).model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # The flag is advisory, so a profile without ``data_quality`` must not turn into a 500.
    data_quality = profile.get("data_quality") or {}
    data_quality["price_snapshot"] = _price_snapshot_flags(symbol)
    profile["data_quality"] = data_quality
    return profile


@router.get("/technicals")
def technicals(ticker: str = Query(..., description="Full ticker, e.g. ADBE.N")) -> Dict[str, Any]:
    """Technical indicators for one instrument from its daily closes.

    Moving averages and trend, RSI, MACD, Bollinger bands, the 52-week range,
    period returns and relative strength against the valuation benchmark,
    with plain-language ``signals`` and data-quality warnings. The same
    readings back the assistant's ``get_instrument_technicals`` MCP tool.
    """

    require_core(instrument_technicals, "Instrument technicals")

    symbol = ticker.strip().upper()
    if not symbol or symbol.startswith("."):
        raise HTTPException(status_code=400, detail="No ticker supplied")
    try:
        return instrument_technicals(symbol).model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/credit-risk")
def credit_risk(ticker: str = Query(..., description="Full ticker, e.g. BP.L")) -> Dict[str, Any]:
    """Per-company credit/distress verdict for one instrument (#10606, allotmint-pro#701).

    ``result`` is the pro tool's row: ``band`` (high/watch/low/unknown),
    ``reasons``, ``mitigations``, ``signals`` (Altman Z, interest cover, net
    debt / EBITDA, current ratio, FCF, 52-week fall) and ``data_gaps``.
    ``market_context`` holds the latest stored credit spreads, ``thresholds``
    the cut-offs and ``note`` the caveat to show with it. The same verdict
    backs the assistant's ``get_credit_risk`` MCP tool.
    """

    require_core(get_credit_risk, "Credit risk")

    symbol = ticker.strip().upper()
    if not symbol or symbol.startswith("."):
        raise HTTPException(status_code=400, detail="No ticker supplied")
    try:
        verdict = get_credit_risk(ticker=symbol)
    except (ToolError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not verdict.get("results"):
        failed = verdict.get("failed") or [{}]
        raise HTTPException(status_code=502, detail=failed[0].get("error") or "No fundamentals for this ticker")
    return {
        "result": verdict["results"][0],
        "market_context": verdict.get("market_context"),
        "thresholds": verdict.get("thresholds"),
        "note": verdict.get("note"),
    }
