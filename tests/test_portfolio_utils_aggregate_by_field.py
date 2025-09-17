import backend.common.portfolio_utils as portfolio_utils
from backend.common import instrument_api
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


def test_holding_metadata_overrides_instrument_defaults(monkeypatch):
    monkeypatch.setattr(
        portfolio_utils,
        "get_instrument_meta",
        lambda ticker: {
            "name": f"{ticker} meta",
            "sector": "Instrument Sector",
            "region": "Instrument Region",
            "currency": "EUR",
            "grouping": "Instrument Grouping",
            "grouping_id": "instrument-grouping",
        },
    )
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: (ticker, None),
    )

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "ZZZ.L",
                        "sector": "User Sector",
                        "region": "User Region",
                        "grouping": "User Grouping",
                        "currency": "USD",
                        "market_value_gbp": 10,
                        "cost_gbp": 5,
                        "gain_gbp": 5,
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_ticker(portfolio)
    row = {r["ticker"]: r for r in rows}["ZZZ.L"]
    assert row["sector"] == "User Sector"
    assert row["region"] == "User Region"
    assert row["grouping"] == "User Grouping"
    assert row["currency"] == "USD"

    by_sector = {r["sector"]: r for r in portfolio_utils.aggregate_by_sector(portfolio)}
    assert "User Sector" in by_sector
    assert "Instrument Sector" not in by_sector

    by_region = {r["region"]: r for r in portfolio_utils.aggregate_by_region(portfolio)}
    assert "User Region" in by_region
    assert "Instrument Region" not in by_region
