import pytest

from backend.common import instrument_api
from backend.common import portfolio_utils as pu


@pytest.fixture
def sample_portfolio():
    return {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "ABC", "units": "1.2", "exchange": "L"},
                    {"ticker": "ABC", "units": 0.8},  # missing exchange -> resolved
                    {"ticker": "MNO", "units": 5},  # price lookup will fail
                    {"ticker": "ZERO", "units": 0},  # zero units should be ignored
                ]
            },
            {
                "holdings": [
                    {"ticker": "DEF.US", "units": 2.3456},
                    {"ticker": "DEF", "units": "1.0", "exchange": "US"},
                ]
            },
        ]
    }


def test_portfolio_value_breakdown_aggregates_and_handles_missing(monkeypatch, sample_portfolio):
    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", lambda owner: sample_portfolio)

    resolved = {
        "ABC": ("ABC", "L"),
        "DEF.US": ("DEF", "US"),
        "DEF": ("DEF", "US"),
    }

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: resolved.get(ticker),
    )

    prices = {
        ("ABC", "L"): 10.12345,
        ("DEF", "US"): 50.98765,
    }

    def fake_get_price_for_date_scaled(ticker, exchange, target):
        price = prices.get((ticker, exchange))
        if price is None:
            return None, None
        return price, "test"

    monkeypatch.setattr(pu, "_get_price_for_date_scaled", fake_get_price_for_date_scaled)

    rows = pu.portfolio_value_breakdown("owner", "2024-05-01")

    rows_by_key = {(row["ticker"], row["exchange"]): row for row in rows}

    assert ("ZERO", "L") not in rows_by_key
    assert {key for key in rows_by_key} == {("ABC", "L"), ("DEF", "US"), ("MNO", "L")}

    abc = rows_by_key[("ABC", "L")]
    assert abc["units"] == pytest.approx(2.0)
    assert abc["price"] == pytest.approx(10.1235)
    assert abc["value"] == pytest.approx(20.25)

    deff = rows_by_key[("DEF", "US")]
    assert deff["units"] == pytest.approx(3.3456)
    assert deff["price"] == pytest.approx(50.9877)
    assert deff["value"] == pytest.approx(170.58)

    mno = rows_by_key[("MNO", "L")]
    assert mno["units"] == pytest.approx(5.0)
    assert mno["price"] is None
    assert mno["value"] is None


def test_portfolio_value_breakdown_invalid_date(monkeypatch):
    called = False

    def fake_builder(owner):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", fake_builder)

    with pytest.raises(ValueError) as excinfo:
        pu.portfolio_value_breakdown("owner", "not-a-date")

    assert str(excinfo.value) == "Invalid date: not-a-date"
    assert called is False
