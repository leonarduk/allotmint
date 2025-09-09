"""Simple scenario testing endpoint."""

from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.common.data_loader import list_plots
from backend.common.portfolio import build_owner_portfolio
from backend.utils.scenario_tester import (
    apply_historical_event_portfolio as apply_historical_event,
    apply_price_shock,
)

router = APIRouter(tags=["scenario"])


@router.get("/scenario")
def run_scenario(
    ticker: str = Query(..., description="Ticker symbol"),
    pct: float = Query(..., description="Percentage change"),
):
    """Apply a percentage price shock to all portfolios for ``ticker``."""
    results = []
    owners = [p["owner"] for p in list_plots() if p.get("accounts")]
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


@router.get("/scenario/historical")
def run_historical_scenario(
    event_id: str | None = Query(None, description="Historical event identifier"),
    date: str | None = Query(None, description="Event date (YYYY-MM-DD)"),
    horizons: List[int] = Query(..., description="Event horizons in days"),
):
    """Calculate shocked portfolio values for a historical event."""

    if event_id is None and date is None:
        raise HTTPException(status_code=400, detail="event_id or date must be provided")
    if not horizons:
        raise HTTPException(status_code=400, detail="horizons must be provided")

    results = []
    owners = [p["owner"] for p in list_plots() if p.get("accounts")]
    for owner in owners:
        try:
            pf = build_owner_portfolio(owner)
        except FileNotFoundError:
            continue

        baseline = pf.get("total_value_estimate_gbp")
        if baseline is None:
            baseline = sum(a.get("value_estimate_gbp") or 0.0 for a in pf.get("accounts", []))
            pf["total_value_estimate_gbp"] = baseline

        shocked = apply_historical_event(pf, event_id=event_id, date=date, horizons=horizons)
        horizon_map = {}
        for h, shocked_pf in shocked.items():
            val = shocked_pf.get("total_value_estimate_gbp")
            pct_change = None
            if baseline not in (None, 0) and val is not None:
                pct_change = (val - baseline) / baseline
            horizon_map[h] = {
                "shocked_total_value_gbp": val,
                "pct_change": pct_change,
            }

        results.append(
            {
                "owner": owner,
                "baseline_total_value_gbp": baseline,
                "horizons": horizon_map,
            }
        )

    return results
