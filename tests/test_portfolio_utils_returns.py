import pandas as pd
import pytest
from datetime import date, timedelta

from backend.common import instrument_api
from backend.common import portfolio_utils as pu


@pytest.fixture
def portfolio_series():
    base = date(2024, 1, 1)
    idx = pd.Index([base + timedelta(days=i) for i in range(3)])
    return pd.Series([1000.0, 1050.0, 1100.0], index=idx)


@pytest.fixture
def sample_transactions():
    return [
        {"date": "2024-01-02", "type": "deposit", "amount_minor": 1000},
        {"date": "2024-02-01", "kind": "withdrawal", "amount_minor": 500},
        {"date": "2023-12-15", "type": "deposit", "amount_minor": 2000},
    ]


def test_compute_time_weighted_return_with_cashflows(monkeypatch, portfolio_series, sample_transactions):
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: portfolio_series)
    monkeypatch.setattr(pu, "load_transactions", lambda owner: sample_transactions)

    result = pu.compute_time_weighted_return("owner")

    assert result == pytest.approx(0.089523, rel=1e-4)


def test_compute_time_weighted_return_requires_two_points(monkeypatch):
    idx = pd.Index([date(2024, 1, 1)])
    series = pd.Series([1000.0], index=idx)
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: series)
    monkeypatch.setattr(pu, "load_transactions", lambda owner: [])

    assert pu.compute_time_weighted_return("owner") is None


@pytest.fixture
def one_year_series():
    start = date(2024, 1, 1)
    end = date(2025, 1, 1)
    idx = pd.Index([start, end])
    return pd.Series([1000.0, 1100.0], index=idx)


def test_compute_xirr_simple_contribution(monkeypatch, one_year_series):
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: one_year_series)
    transactions = [
        {"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 100000},
        {"date": "2023-12-01", "type": "deposit", "amount_minor": 1000},
        {"date": "2025-02-01", "kind": "WITHDRAWAL", "amount_minor": 1000},
    ]
    monkeypatch.setattr(pu, "load_transactions", lambda owner: transactions)

    result = pu.compute_xirr("owner")

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_xirr_requires_cashflows(monkeypatch, one_year_series):
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: one_year_series)
    monkeypatch.setattr(pu, "load_transactions", lambda owner: [])

    assert pu.compute_xirr("owner") is None


def test_compute_cagr(monkeypatch, one_year_series):
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: one_year_series)

    result = pu.compute_cagr("owner")

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_cagr_invalid_series(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    series = pd.Series([0.0, 1000.0], index=idx)
    monkeypatch.setattr(pu, "_portfolio_value_series", lambda owner, days=365: series)

    assert pu.compute_cagr("owner") is None


def test_compute_cash_apy(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    cash_series = pd.Series([5000.0, 5250.0], index=idx)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: cash_series)

    result = pu.compute_cash_apy("owner")

    assert result == pytest.approx(0.05, abs=1e-3)


def test_compute_cash_apy_empty(monkeypatch):
    empty_series = pd.Series(dtype=float)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: empty_series)

    assert pu.compute_cash_apy("owner") is None

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

