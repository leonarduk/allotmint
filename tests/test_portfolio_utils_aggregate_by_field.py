import backend.common.portfolio_utils as portfolio_utils
import pytest


def _sample_portfolio():
    return {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "sector": "Tech",
                        "region": "US",
                        "market_value_gbp": 150,
                        "cost_gbp": 100,
                        "gain_gbp": 50,
                    },
                    {
                        "ticker": "BBB",
                        "sector": "Finance",
                        "market_value_gbp": 220,
                        "cost_gbp": 200,
                        "gain_gbp": 20,
                    },
                    {
                        "ticker": "CCC",
                        "region": "EU",
                        "market_value_gbp": 70,
                        "cost_gbp": 50,
                        "gain_gbp": 20,
                    },
                ]
            }
        ]
    }


def test_aggregate_by_sector_totals_and_percentages():
    sector_rows = portfolio_utils.aggregate_by_sector(_sample_portfolio())
    sectors = {row["sector"]: row for row in sector_rows}

    assert set(sectors) == {"Tech", "Finance", "Unknown"}

    assert sectors["Tech"]["market_value_gbp"] == 150
    assert sectors["Tech"]["cost_gbp"] == 100
    assert sectors["Tech"]["gain_gbp"] == 50
    assert sectors["Tech"]["gain_pct"] == pytest.approx(50)
    assert sectors["Tech"]["contribution_pct"] == pytest.approx(14.2857, rel=1e-3)

    assert sectors["Finance"]["market_value_gbp"] == 220
    assert sectors["Finance"]["cost_gbp"] == 200
    assert sectors["Finance"]["gain_gbp"] == 20
    assert sectors["Finance"]["gain_pct"] == pytest.approx(10)
    assert sectors["Finance"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)

    assert sectors["Unknown"]["market_value_gbp"] == 70
    assert sectors["Unknown"]["cost_gbp"] == 50
    assert sectors["Unknown"]["gain_gbp"] == 20
    assert sectors["Unknown"]["gain_pct"] == pytest.approx(40)
    assert sectors["Unknown"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)


def test_aggregate_by_region_totals_and_percentages():
    region_rows = portfolio_utils.aggregate_by_region(_sample_portfolio())
    regions = {row["region"]: row for row in region_rows}

    assert set(regions) == {"US", "EU", "Unknown"}

    assert regions["US"]["market_value_gbp"] == 150
    assert regions["US"]["cost_gbp"] == 100
    assert regions["US"]["gain_gbp"] == 50
    assert regions["US"]["gain_pct"] == pytest.approx(50)
    assert regions["US"]["contribution_pct"] == pytest.approx(14.2857, rel=1e-3)

    assert regions["EU"]["market_value_gbp"] == 70
    assert regions["EU"]["cost_gbp"] == 50
    assert regions["EU"]["gain_gbp"] == 20
    assert regions["EU"]["gain_pct"] == pytest.approx(40)
    assert regions["EU"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)

    assert regions["Unknown"]["market_value_gbp"] == 220
    assert regions["Unknown"]["cost_gbp"] == 200
    assert regions["Unknown"]["gain_gbp"] == 20
    assert regions["Unknown"]["gain_pct"] == pytest.approx(10)
    assert regions["Unknown"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)
