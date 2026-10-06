"""FX rates the frontend needs to report in a base currency other than GBP (#9768)."""

import re

from fastapi import APIRouter, HTTPException, Query

from backend.common.currency import CurrencyNormaliser
from backend.common.portfolio_utils import fx_rate_to_gbp_with_source
from backend.timeseries.cache import cache_only

router = APIRouter(prefix="/fx", tags=["fx"])

_CURRENCY_CODE = re.compile(r"[A-Za-z]{3}")


@router.get("/gbp-rate")
def gbp_rate(currency: str = Query(..., description="3-letter currency code, e.g. USD")):
    """GBP per one unit of ``currency``, as the portfolio's holdings are valued.

    Every portfolio amount is GBP, so a base currency other than GBP needs this
    one rate: ``value_in_base = value_gbp / gbp_per_unit``. Read from the FX
    cache (never Yahoo on a page request, #8028), then an approximate fallback
    constant (``source == "fallback"``); ``gbp_per_unit`` is ``null`` with
    ``source == "missing"`` when there is no rate (#9664). GBP and pence
    (GBX) are GBP: ``1.0`` with no source.
    """
    code = currency.strip()
    if not _CURRENCY_CODE.fullmatch(code):
        raise HTTPException(status_code=400, detail="currency must be a 3-letter code")
    norm = CurrencyNormaliser.from_raw(code)
    resolved = "GBP" if norm.is_pence else norm.canonical
    with cache_only():
        rate, source = fx_rate_to_gbp_with_source(resolved)
    return {"currency": resolved, "gbp_per_unit": rate, "source": source}
