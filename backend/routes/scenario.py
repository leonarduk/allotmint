"""Simple scenario testing endpoint."""

import datetime as _dt
import re
from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.common.data_loader import ProviderUnavailable, list_plots
from backend.common.portfolio import build_owner_portfolio
from backend.common.portfolio_utils import UNCONVERTED_HOLDINGS_KEY
from backend.routes.events import get_event
from backend.utils.scenario_tester import (
    _HORIZONS,
    FX_SHOCK_KEY,
    NON_SHOCKABLE_CURRENCIES,
    apply_fx_shock,
    apply_price_shock,
)
from backend.utils.scenario_tester import apply_historical_event_portfolio as apply_historical_event

router = APIRouter(tags=["scenario"])


@router.get("/scenario")
def run_scenario(
    ticker: str = Query(..., description="Ticker symbol"),
    pct: float = Query(..., description="Percentage change"),
):
    """Apply a percentage price shock to all portfolios for ``ticker``."""
    results = []
    try:
        owners = [p.owner for p in list_plots() if p.accounts]
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
    for owner in owners:
        try:
            pf = build_owner_portfolio(owner)
        except FileNotFoundError:
            # Skip owners with incomplete account data
            continue
        baseline = pf.get("total_value_estimate_gbp")
        # ensure baseline exists before applying shock
        if baseline is None:
            baseline = sum(a.get("value_estimate_gbp") or 0.0 for a in pf.get("accounts", []))
            pf["total_value_estimate_gbp"] = baseline
        shocked = apply_price_shock(pf, ticker, pct)
        shocked_total = shocked.get("total_value_estimate_gbp")
        delta = None
        if baseline is not None and shocked_total is not None:
            delta = round(shocked_total - baseline, 2)
        results.append(
            {
                "owner": owner,
                "baseline_total_value_gbp": baseline,
                "shocked_total_value_gbp": shocked_total,
                "delta_gbp": delta,
            }
        )
    return results


_CURRENCY_CODE = re.compile(r"[A-Za-z]{3}")


def _shockable_currency(currency: str) -> str:
    """``currency`` upper-cased, or a 400 when it is not a 3-letter code or is sterling."""
    code = currency.strip()
    if not _CURRENCY_CODE.fullmatch(code):
        raise HTTPException(status_code=400, detail="currency must be a 3-letter code")
    code = code.upper()
    if code in NON_SHOCKABLE_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"{code} cannot move against GBP")
    return code


def _fx_shock_result(owner: str, pf: dict, currency: str, pct: float) -> dict:
    shocked = apply_fx_shock(pf, currency, pct)
    summary = shocked[FX_SHOCK_KEY]
    baseline = summary["baseline_total_value_gbp"]
    shocked_total = shocked["total_value_estimate_gbp"]
    return {
        "owner": owner,
        "baseline_total_value_gbp": baseline,
        "shocked_total_value_gbp": shocked_total,
        "delta_gbp": round(shocked_total - baseline, 2),
        "exposed_value_gbp": summary["exposed_value_gbp"],
        "skipped_unknown_currency": summary["skipped_unknown_currency"],
        UNCONVERTED_HOLDINGS_KEY: summary[UNCONVERTED_HOLDINGS_KEY],
    }


@router.get("/scenario/fx")
def run_fx_scenario(
    currency: str = Query(..., description="3-letter code of the currency that moves against GBP, e.g. USD"),
    pct: float = Query(
        ...,
        gt=-100,
        le=1000,
        description="Change in the GBP value of one unit of `currency`, in percent (-10 = it weakens 10% vs GBP)",
    ),
):
    """Revalue every owner's portfolio for ``currency`` moving ``pct`` percent against GBP (#9725).

    Sign convention: ``pct`` is the change in the GBP value of one unit of
    ``currency``. ``currency=USD&pct=-10`` means USD weakens 10% against GBP,
    so each holding quoted in USD (``CASH.USD`` included) is worth 0.9x its
    GBP value; GBP and GBX holdings never move. ``pct`` must be in
    (-100, 1000]; GBP/GBX or a code that is not 3 letters is a 400.

    Each owner's result has the ``/scenario`` fields plus
    ``exposed_value_gbp`` (baseline GBP value of the holdings quoted in
    ``currency``), ``skipped_unknown_currency`` (holdings not shocked because
    their currency is unknown) and ``unconverted_holdings`` (holdings with no
    usable FX rate, left out of both totals). Uses the GBP values already on
    the portfolio, so no FX rate is fetched.
    """
    code = _shockable_currency(currency)
    try:
        owners = [p.owner for p in list_plots() if p.accounts]
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
    results = []
    for owner in owners:
        try:
            pf = build_owner_portfolio(owner)
        except FileNotFoundError:
            continue
        results.append(_fx_shock_result(owner, pf, code, pct))
    return results


# Fallback proxy for an ad-hoc ``date`` with no catalogue entry.
_DEFAULT_PROXY_INDEX = "SPY.N"


def _resolve_event(event_id: str | None, date: str | None) -> dict:
    """Return the event to replay: the catalogue entry for ``event_id`` or an ad-hoc ``date``."""
    if event_id is not None:
        event = get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="unknown event")
        if not event.get("date"):
            raise HTTPException(status_code=422, detail="event has no date")
        return event
    try:
        _dt.date.fromisoformat(str(date))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc
    return {"id": date, "date": date, "proxy_index": _DEFAULT_PROXY_INDEX}


@router.get("/scenario/historical")
def run_historical_scenario(
    event_id: str | None = Query(None, description="Historical event identifier"),
    date: str | None = Query(None, description="Event date (YYYY-MM-DD)"),
    horizons: List[str] = Query(..., description="Event horizons as day counts or tokens like '1w'"),
):
    """Calculate shocked portfolio values for a historical event.

    ``horizons`` accepts either integer day counts or one of the preset tokens
    ``1d``, ``1w``, ``1m``, ``3m`` or ``1y``. Values may be provided as a
    comma-separated string (e.g. ``horizons=1d,1w,30``). Unrecognised tokens
    will raise ``HTTPException(status_code=400, detail="invalid horizon")``.
    """

    if event_id is None and date is None:
        raise HTTPException(status_code=400, detail="event_id or date must be provided")

    # split comma separated horizons and convert tokens to day counts
    tokens: list[str] = []
    for item in horizons:
        tokens.extend([t.strip().lower() for t in str(item).split(",") if t.strip()])

    if not tokens:
        raise HTTPException(status_code=400, detail="horizons must be provided")

    label_pairs: list[tuple[str, int]] = []
    for tok in tokens:
        if tok in _HORIZONS:
            label_pairs.append((tok, _HORIZONS[tok]))
        else:
            try:
                days = int(tok)
            except ValueError as exc:  # pragma: no cover - defensive
                raise HTTPException(status_code=400, detail="invalid horizon") from exc
            label_pairs.append((tok, days))

    horizon_days = dict(label_pairs)
    event = _resolve_event(event_id, date)

    results = []
    try:
        owners = [p.owner for p in list_plots() if p.accounts]
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
    for owner in owners:
        try:
            pf = build_owner_portfolio(owner)
        except FileNotFoundError:
            continue

        baseline = pf.get("total_value_estimate_gbp")
        if baseline is None:
            baseline = sum(a.get("value_estimate_gbp") or 0.0 for a in pf.get("accounts", []))
            pf["total_value_estimate_gbp"] = baseline

        shocked = apply_historical_event(pf, event=event, horizons=horizon_days)
        horizon_map = {}
        for label in horizon_days:
            shocked_label = shocked.get(label) or {}
            horizon_map[label] = {
                "baseline_total_value_gbp": baseline,
                "shocked_total_value_gbp": shocked_label.get("total_value_gbp"),
                "coverage_pct": shocked_label.get("coverage_pct"),
            }

        results.append(
            {
                "owner": owner,
                "baseline_total_value_gbp": baseline,
                "horizons": horizon_map,
            }
        )

    return results
