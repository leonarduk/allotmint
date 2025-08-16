"""Simple scenario testing endpoint."""

from fastapi import APIRouter, Query

from backend.utils.scenario_tester import apply_price_shock
from backend.common.portfolio_loader import list_portfolios

router = APIRouter(tags=["scenario"])


@router.get("/scenario")
def run_scenario(
    ticker: str = Query(..., description="Ticker symbol"),
    pct: float = Query(..., description="Percentage change"),
):
    """Apply a percentage price shock to all portfolios for ``ticker``."""
    results = []
    for pf in list_portfolios():
        shocked = apply_price_shock(pf, ticker, pct)
        baseline = pf.get("total_value_estimate_gbp")
        shocked_total = shocked.get("total_value_estimate_gbp")
        delta = None
        if baseline is not None and shocked_total is not None:
            delta = round(shocked_total - baseline, 2)
        results.append(
            {
                "owner": pf.get("owner"),
                "baseline_total_value_gbp": baseline,
                "shocked_total_value_gbp": shocked_total,
                "delta_gbp": delta,
            }
        )
    return results
