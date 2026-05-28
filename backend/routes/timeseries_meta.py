import html
import logging
import re
from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pandas.api import types as pd_types

from backend.common import instrument_api
from backend.logging_setup import sanitise_log_value
from backend.timeseries import fetch_timeseries
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.html_render import render_timeseries_html
from backend.utils.timeseries_helpers import (
    apply_scaling,
    get_scaling_override,
    resolve_date_range,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])
logger = logging.getLogger("routes.timeseries")

# Only A-Z, 0-9, and hyphens are valid in a ticker segment or exchange code.
# This allowlist prevents log injection from flowing into any log sink (CWE-117).
_TICKER_SEGMENT_RE = re.compile(r"^[A-Z0-9-]{1,20}$")


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> tuple[str, str]:
    t = (ticker or "").upper()
    if not t:
        raise HTTPException(status_code=400, detail="Ticker is required")

    if exchange:
        sym = t.split(".", 1)[0]
        ex = exchange.upper()
        source = "provided exchange"
    elif "." in t:
        sym, ex = t.split(".", 1)
        source = "inferred from ticker"
    else:
        resolved = instrument_api._resolve_full_ticker(
            t, instrument_api._LATEST_PRICES
        )
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail="Exchange not provided and could not be inferred",
            )
        sym, ex = resolved
        source = "inferred exchange"

    # Validate before logging — sym/ex are [A-Z0-9-] only after this point (CWE-117).
    if not _TICKER_SEGMENT_RE.match(sym) or not _TICKER_SEGMENT_RE.match(ex):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    logger.debug("Resolved %s.%s (%s)", sanitise_log_value(sym), sanitise_log_value(ex), source)
    return sym, ex