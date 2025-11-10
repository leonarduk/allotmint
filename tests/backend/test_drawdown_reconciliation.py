import logging
from datetime import date

import pandas as pd
import pytest

from backend.common import portfolio_utils
from backend.common import portfolio as portfolio_mod


@pytest.fixture
def price_data():
    idx = pd.date_range("2024-01-01", periods=5, freq="D").date
    return {
        "AAA": pd.DataFrame({"Date": idx, "Close": [100, 120, 110, 130, 115]}),
        "BADZERO": pd.DataFrame({"Date": idx, "Close": [100, 0, 95, 105, 100]}),
        "FLAG": pd.DataFrame({"Date": idx, "Close": [50, 40, 30, 20, 10]}),
    }


@pytest.fixture
def mock_env(monkeypatch, price_data):
    owners = {
        "normal": [{"ticker": "AAA", "exchange": "L", "units": 1}],
        "mixed": [
            {"ticker": "AAA", "exchange": "L", "units": 1},
            {"ticker": "BADZERO", "exchange": "L", "units": 1},
            {"ticker": "FLAG", "exchange": "L", "units": 1},
        ],
    }

    def fake_build_owner_portfolio(owner):
        return {"accounts": [{"holdings": owners[owner]}]}

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build_owner_portfolio)

    def fake_resolve(ticker, latest):
        return ticker.split(".")[0], "L"

    monkeypatch.setattr("backend.common.instrument_api._resolve_full_ticker", fake_resolve)

    calls = []

    def fake_load_meta_timeseries(ticker, exchange, days):
        calls.append((ticker, exchange))
        return price_data.get(ticker, pd.DataFrame())

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    portfolio_utils._PRICE_SNAPSHOT = {"FLAG.L": {"flagged": True}}

    return calls


def test_compute_max_drawdown_normal_series(mock_env):
    val = portfolio_utils.compute_max_drawdown("normal", days=5)
    assert val == pytest.approx(-0.11538, rel=1e-4)
    assert mock_env == [("AAA", "L")]


def test_compute_max_drawdown_ignores_flagged(mock_env):
    val = portfolio_utils.compute_max_drawdown("mixed", days=5)
    assert val == pytest.approx(-0.4, rel=1e-4)
    assert ("FLAG", "L") not in mock_env


def reconcile(owner, price_data):
    for tkr, df in price_data.items():
        bad = df[df["Close"] <= 0]
        if not bad.empty:
            d = bad.iloc[0]["Date"]
            logging.warning("Bad series for %s on %s", tkr, d)
    return portfolio_utils.compute_max_drawdown(owner, days=5)


def test_reconciliation_warns_bad_series(price_data, mock_env, caplog):
    with caplog.at_level("WARNING"):
        reconcile("mixed", price_data)
    assert any("BADZERO" in r.message and "2024-01-02" in r.message for r in caplog.records)
