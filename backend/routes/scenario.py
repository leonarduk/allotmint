"""Simple scenario testing endpoint."""

from fastapi import APIRouter, Query

from backend.common.portfolio import build_owner_portfolio, list_owners
from backend.utils.scenario_tester import apply_price_shock

router = APIRouter(tags=["scenario"])


@router.get("/scenario")
def run_scenario(
    ticker: str = Query(..., description="Ticker symbol"),
    pct: float = Query(..., description="Percentage change"),
):
    """Apply a percentage price shock to all portfolios for ``ticker``."""
    results = []
    for owner in list_owners():
        pf = build_owner_portfolio(owner)
        baseline = pf.get("total_value_estimate_gbp")
        # ensure baseline exists before applying shock
        if baseline is None:
            baseline = sum(
                a.get("value_estimate_gbp") or 0.0 for a in pf.get("accounts", [])
            )
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
