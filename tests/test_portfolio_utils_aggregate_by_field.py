import pytest

import backend.common.portfolio_utils as portfolio_utils
from backend.common import instrument_api


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
    assert sectors["Tech"]["weight_pct"] == pytest.approx(34.0909, rel=1e-3)

    assert sectors["Finance"]["market_value_gbp"] == 220
    assert sectors["Finance"]["cost_gbp"] == 200
    assert sectors["Finance"]["gain_gbp"] == 20
    assert sectors["Finance"]["gain_pct"] == pytest.approx(10)
    assert sectors["Finance"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)
    assert sectors["Finance"]["weight_pct"] == pytest.approx(50.0)

    assert sectors["Unknown"]["market_value_gbp"] == 70
    assert sectors["Unknown"]["cost_gbp"] == 50
    assert sectors["Unknown"]["gain_gbp"] == 20
    assert sectors["Unknown"]["gain_pct"] == pytest.approx(40)
    assert sectors["Unknown"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)
    assert sectors["Unknown"]["weight_pct"] == pytest.approx(15.9091, rel=1e-3)


def test_aggregate_by_region_totals_and_percentages():
    region_rows = portfolio_utils.aggregate_by_region(_sample_portfolio())
    regions = {row["region"]: row for row in region_rows}

    assert set(regions) == {"US", "EU", "Unknown"}

    assert regions["US"]["market_value_gbp"] == 150
    assert regions["US"]["cost_gbp"] == 100
    assert regions["US"]["gain_gbp"] == 50
    assert regions["US"]["gain_pct"] == pytest.approx(50)
    assert regions["US"]["contribution_pct"] == pytest.approx(14.2857, rel=1e-3)
    assert regions["US"]["weight_pct"] == pytest.approx(34.0909, rel=1e-3)

    assert regions["EU"]["market_value_gbp"] == 70
    assert regions["EU"]["cost_gbp"] == 50
    assert regions["EU"]["gain_gbp"] == 20
    assert regions["EU"]["gain_pct"] == pytest.approx(40)
    assert regions["EU"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)
    assert regions["EU"]["weight_pct"] == pytest.approx(15.9091, rel=1e-3)

    assert regions["Unknown"]["market_value_gbp"] == 220
    assert regions["Unknown"]["cost_gbp"] == 200
    assert regions["Unknown"]["gain_gbp"] == 20
    assert regions["Unknown"]["gain_pct"] == pytest.approx(10)
    assert regions["Unknown"]["contribution_pct"] == pytest.approx(5.7143, rel=1e-3)
    assert regions["Unknown"]["weight_pct"] == pytest.approx(50.0)


def test_weight_pct_is_share_of_market_value_and_sums_to_100():
    """weight_pct must use market value, not cost.

    Regression guard for the research tool reading contribution_pct (a
    gain contribution measured against cost) as if it were a portfolio
    weight, which produced sector "weights" of ~1e-06.
    """

    rows = portfolio_utils.aggregate_by_sector(_sample_portfolio())

    assert sum(row["weight_pct"] for row in rows) == pytest.approx(100.0)
    for row in rows:
        assert row["weight_pct"] != pytest.approx(row["contribution_pct"])


def test_weight_pct_is_none_when_portfolio_has_no_market_value():
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "sector": "Tech",
                        "market_value_gbp": 0,
                        "cost_gbp": 0,
                        "gain_gbp": 0,
                    }
                ]
            }
        ]
    }

    rows = portfolio_utils.aggregate_by_sector(portfolio)

    assert [row["weight_pct"] for row in rows] == [None]


def test_aggregate_by_region_merges_uk_aliases():
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "CASH.GBP",
                        "region": "United Kingdom",
                        "units": 425858.04,
                        "market_value_gbp": 425858.04,
                        "cost_gbp": 425858.04,
                        "gain_gbp": 0,
                    },
                    {
                        "ticker": "AAA.L",
                        "region": "UK",
                        "market_value_gbp": 259547.75,
                        "cost_gbp": 200000,
                        "gain_gbp": 59547.75,
                    },
                ]
            }
        ]
    }

    region_rows = portfolio_utils.aggregate_by_region(portfolio)
    regions = {row["region"]: row for row in region_rows}

    assert set(regions) == {"United Kingdom"}
    assert regions["United Kingdom"]["market_value_gbp"] == pytest.approx(425858.04 + 259547.75)
    assert regions["United Kingdom"]["cost_gbp"] == pytest.approx(425858.04 + 200000)


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
