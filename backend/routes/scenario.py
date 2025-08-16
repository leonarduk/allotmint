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
        results.append(
            {
                "owner": pf.get("owner"),
                "total_value_estimate_gbp": shocked.get("total_value_estimate_gbp"),
            }
        )
    return results
