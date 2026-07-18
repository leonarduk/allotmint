"""Read-only timeseries data quality endpoint.

Reports, for each cached instrument's timeseries, gap/duplicate/outlier
metrics so problems can be surfaced by a UI (see #4898) or a scheduled job,
independently of any frontend. Never fetches new data or mutates the cache.
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    has_cached_meta_timeseries,
    list_cached_meta_tickers,
    load_cached_meta_timeseries_full,
)
from backend.timeseries.quality import (
    DEFAULT_GAP_THRESHOLD_DAYS,
    DEFAULT_OUTLIER_SIGMA,
    DEFAULT_ROLLING_WINDOW,
    compute_quality,
)

router = APIRouter(prefix="/data-quality", tags=["data-quality"])
logger = logging.getLogger("routes.data_quality")

# Same allowlist shape as backend/routes/timeseries_meta.py — bounds
# user-supplied ticker/exchange segments before they reach a cache file path.
_TICKER_RE = re.compile(r"^[A-Z0-9_-]{1,50}$")
_EXCHANGE_RE = re.compile(r"^[A-Z0-9._-]{1,50}$")


def _validate_symbol(value: str, *, kind: str) -> str:
    upper = value.upper()
    pattern = _TICKER_RE if kind == "ticker" else _EXCHANGE_RE
    if not pattern.match(upper):
        raise HTTPException(status_code=400, detail=f"Invalid {kind} format")
    return upper


@router.get("/timeseries")
async def get_timeseries_quality(
    ticker: str | None = Query(None, description="Filter to a single ticker (must be provided with exchange)"),
    exchange: str | None = Query(None, description="Filter to a single exchange (must be provided with ticker)"),
    gap_threshold_days: int = Query(
        DEFAULT_GAP_THRESHOLD_DAYS,
        ge=0,
        le=30,
        description="A run of missing business days longer than this counts as a gap",
    ),
    outlier_sigma: float = Query(
        DEFAULT_OUTLIER_SIGMA,
        gt=0,
        le=10,
        description="Standard deviations from the rolling mean beyond which a point is an outlier",
    ),
    rolling_window: int = Query(
        DEFAULT_ROLLING_WINDOW, ge=2, le=250, description="Rolling window size (trading days) for outlier detection"
    ),
    max_results: int | None = Query(
        None, ge=1, le=1000, description="Limit the number of distinct ticker/exchange pairs processed"
    ),
):
    if bool(ticker) != bool(exchange):
        raise HTTPException(status_code=400, detail="ticker and exchange must be provided together")

    if ticker and exchange:
        tkr = _validate_symbol(ticker, kind="ticker")
        exch = _validate_symbol(exchange, kind="exchange")
        if not has_cached_meta_timeseries(tkr, exch):
            raise HTTPException(status_code=404, detail="No cached timeseries found for that ticker/exchange")
        pairs = [(tkr, exch)]
    else:
        pairs = list_cached_meta_tickers()

    truncated = max_results is not None and len(pairs) > max_results
    if max_results is not None:
        pairs = pairs[:max_results]

    results = []
    for tkr, exch in pairs:
        try:
            df = load_cached_meta_timeseries_full(tkr, exch)
        except Exception as exc:
            logger.warning(
                "Failed to load cached timeseries for %s.%s: %s",
                sanitise_log_value(tkr),
                sanitise_log_value(exch),
                sanitise_log_value(exc),
            )
            continue
        results.append(
            compute_quality(
                df,
                tkr,
                exch,
                gap_threshold_days=gap_threshold_days,
                outlier_sigma=outlier_sigma,
                rolling_window=rolling_window,
            )
        )

    return JSONResponse(content={"count": len(results), "positions": results, "truncated": truncated})
