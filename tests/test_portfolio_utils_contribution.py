import backend.common.portfolio_utils as portfolio_utils
import pytest


def test_aggregate_by_sector_and_region():
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "units": 1,
                        "sector": "Tech",
                        "region": "US",
                        "market_value_gbp": 150,
                        "cost_gbp": 100,
                        "gain_gbp": 50,
                    },
                    {
                        "ticker": "BBB",
                        "units": 1,
                        "sector": "Health",
                        "region": "UK",
                        "market_value_gbp": 180,
                        "cost_gbp": 200,
                        "gain_gbp": -20,
                    },
                ]
            }
        ]
    }

    sector_rows = portfolio_utils.aggregate_by_sector(portfolio)
    region_rows = portfolio_utils.aggregate_by_region(portfolio)

    sectors = {row["sector"]: row for row in sector_rows}
    regions = {row["region"]: row for row in region_rows}

    assert sectors["Tech"]["gain_gbp"] == 50
    assert sectors["Health"]["gain_gbp"] == -20
    assert regions["US"]["gain_gbp"] == 50
    assert regions["UK"]["gain_gbp"] == -20

    assert sectors["Tech"]["contribution_pct"] == pytest.approx(16.666, rel=1e-3)
    assert sectors["Health"]["contribution_pct"] == pytest.approx(-6.666, rel=1e-3)
    assert regions["US"]["contribution_pct"] == pytest.approx(16.666, rel=1e-3)
    assert regions["UK"]["contribution_pct"] == pytest.approx(-6.666, rel=1e-3)
