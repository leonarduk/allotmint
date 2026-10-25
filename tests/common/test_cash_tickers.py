"""CASH as a cash balance vs CASH as a stock (Pathward Financial, CASH.N) (#10516)."""

import datetime as dt
import json

import pandas as pd
import pytest

from backend.common import instruments
from backend.common.cash_tickers import cash_price_key, cash_ticker_currency, is_cash_listing, is_cash_ticker
from backend.common.instrument_classification import classify_instrument
from backend.common.sector_labels import is_cash_instrument

CASH_BALANCES = ["CASH", "cash", "CASH.GBP", "cash.usd", "CASH.EUR", " CASH.GBP ", "GBP.CASH", "USD.CASH"]
CASH_STOCKS = ["CASH.N", "CASH.US", "CASH.L", "CASH.ASX", "cash.n"]


@pytest.fixture
def instruments_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    instruments.get_instrument_meta.cache_clear()
    instruments._persisted_metadata_exchanges.cache_clear()
    yield tmp_path
    instruments.get_instrument_meta.cache_clear()
    instruments._persisted_metadata_exchanges.cache_clear()


@pytest.mark.parametrize("ticker", CASH_BALANCES)
def test_currency_suffix_is_cash(ticker):
    assert is_cash_ticker(ticker)
    assert is_cash_instrument(ticker)


@pytest.mark.parametrize("ticker", [*CASH_STOCKS, "CASHX.L", "VOD.L", "", None, 42])
def test_exchange_suffix_is_not_cash(ticker):
    assert not is_cash_ticker(ticker)
    assert not is_cash_instrument(ticker)


@pytest.mark.parametrize(
    "ticker,folder,name",
    [("CASH", "Cash", "GBP"), ("CASH.GBP", "Cash", "GBP"), ("cash.usd", "Cash", "USD"), ("CASH.EUR", "Cash", "EUR")],
)
def test_cash_balance_path_stays_in_cash_folder(instruments_dir, ticker, folder, name):
    assert instruments._instrument_path(ticker) == instruments_dir / folder / f"{name}.json"


def test_legacy_ccy_cash_path_is_not_cash_slash_cash(instruments_dir):
    # GBP.CASH must not land in the cash branch with exch "CASH" (Cash/CASH.json).
    assert instruments._instrument_path("GBP.CASH") == instruments_dir / "CASH" / "GBP.json"


@pytest.mark.parametrize("exchange", ["N", "US", "L"])
def test_cash_stock_path_uses_exchange_folder(instruments_dir, exchange):
    assert instruments._instrument_path(f"CASH.{exchange}") == instruments_dir / exchange / "CASH.json"


def test_save_pathward_writes_exchange_folder_not_cash(instruments_dir):
    path = instruments.save_instrument_meta("CASH", "N", {"ticker": "CASH.N", "name": "Pathward Financial, Inc."})

    assert path == instruments_dir / "N" / "CASH.json"
    assert json.loads(path.read_text())["name"] == "Pathward Financial, Inc."
    assert not (instruments_dir / "Cash").exists()
    assert instruments.get_instrument_meta("CASH.N")["name"] == "Pathward Financial, Inc."


def test_classify_pathward_as_equity_not_cash():
    result = classify_instrument({"ticker": "CASH.N", "name": "Pathward Financial, Inc.", "instrument_type": "Equity"})

    assert result["asset_class"] == "equity"
    assert result.get("sector") != "Cash"


@pytest.mark.parametrize("ticker", ["CASH.GBP", "CASH.USD", "GBP.CASH"])
def test_classify_cash_balance_as_cash(ticker):
    assert classify_instrument({"ticker": ticker, "name": "Cash"})["asset_class"] == "cash"


def test_auto_create_skips_cash_balance_but_not_cash_stock(monkeypatch, instruments_dir):
    fetched = []

    def fake_fetch(sym, exch):
        fetched.append(f"{sym}.{exch}")
        return {"name": "Pathward Financial, Inc.", "instrument_type": "Equity"}

    monkeypatch.setattr(instruments, "_fetch_metadata_from_yahoo", fake_fetch)
    monkeypatch.setattr(instruments, "_AUTO_CREATE_FAILURES", set())

    assert instruments._auto_create_instrument_meta("CASH.GBP") is None
    assert instruments._auto_create_instrument_meta("CASH.N")["ticker"] == "CASH.N"
    assert fetched == ["CASH.N"]
    assert (instruments_dir / "N" / "CASH.json").exists()
    assert not (instruments_dir / "Cash").exists()


def test_resolve_ticker_finds_cash_stock_but_not_cash_balance(instruments_dir):
    instruments.save_instrument_meta(
        "CASH", "N", {"ticker": "CASH.N", "name": "Pathward Financial, Inc.", "sector": "Financial Services"}
    )

    assert instruments.resolve_instrument_ticker("CASH.N") == "CASH.N"
    assert instruments.resolve_instrument_ticker("CASH") is None
    assert instruments.resolve_instrument_ticker("CASH.GBP") is None


# --- #10538: the remaining CASH special cases go through is_cash_ticker ----


@pytest.mark.parametrize(
    "symbol,exchange,expected",
    [
        ("CASH", "GBP", True),
        ("cash", "usd", True),
        ("GBP", "CASH", True),
        ("CASH", "", True),
        ("CASH.GBP", "L", True),
        ("CASH", "N", False),
        ("CASH", "ASX", False),
        ("CASHX", "L", False),
        ("VOD", "L", False),
        (None, "GBP", False),
    ],
)
def test_is_cash_listing(symbol, exchange, expected):
    assert is_cash_listing(symbol, exchange) is expected


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("CASH.USD", "USD"),
        ("eur.cash", "EUR"),
        ("CASH.GBX", "GBX"),
        ("CASH", None),
        ("CASH.N", None),
        ("CASH.ASX", None),
        ("VOD.L", None),
        (None, None),
    ],
)
def test_cash_ticker_currency_only_returns_real_currencies(ticker, expected):
    assert cash_ticker_currency(ticker) == expected


def _close_loader(close):
    def loader(ticker, exchange, start_date, end_date, **_kwargs):
        return pd.DataFrame({"Date": [pd.Timestamp(end_date)], "Close_gbp": [close], "Source": ["Yahoo"]})

    return loader


def test_cash_stock_is_priced_from_its_series_not_at_one(monkeypatch):
    from backend.common import holding_utils

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", _close_loader(25.5))
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 1.0)
    d = dt.date(2026, 10, 1)

    assert holding_utils._get_price_for_date_scaled("CASH", "N", d)[0] == pytest.approx(25.5)
    assert holding_utils._load_unscaled_price_for_date_impl("CASH", "N", d)[0] == pytest.approx(25.5)


@pytest.mark.parametrize("symbol,exchange", [("CASH", "GBP"), ("CASH", "USD"), ("GBP", "CASH")])
def test_cash_balance_still_priced_at_one_without_a_lookup(monkeypatch, symbol, exchange):
    from backend.common import holding_utils

    def explode(*args, **kwargs):
        raise AssertionError("cash must not hit the timeseries loader")

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", explode)
    d = dt.date(2026, 10, 1)

    assert holding_utils._get_price_for_date_scaled(symbol, exchange, d) == (1.0, None)
    assert holding_utils._load_unscaled_price_for_date_impl(symbol, exchange, d)[0] == 1.0


def test_cash_ticker_ccy_ignores_exchange_suffix():
    from backend.common import holding_utils, portfolio_utils

    assert holding_utils._cash_ticker_ccy("CASH.N") is None
    assert holding_utils._cash_ticker_ccy("CASH.USD") == "USD"
    assert portfolio_utils._cash_currency("CASH.ASX") is None
    assert portfolio_utils._cash_currency("USD.CASH") == "USD"


def test_portfolio_utils_treats_cash_stock_as_equity(monkeypatch):
    from backend.common import portfolio_utils

    monkeypatch.setattr(portfolio_utils, "instrument_currency", lambda t, e: "USD")

    assert not portfolio_utils._is_cash_holding("CASH", "N")
    assert portfolio_utils._is_cash_holding("CASH", "GBP")
    assert portfolio_utils._holding_currency("CASH", "N").canonical == "USD"
    assert portfolio_utils._holding_currency("CASH", "EUR").canonical == "EUR"


def test_fetch_meta_timeseries_does_not_flatline_cash_stock(monkeypatch):
    from backend.timeseries import fetch_meta_timeseries as fmt

    monkeypatch.setattr(fmt, "_resolve_ticker_exchange", lambda t, e: (t, e))
    flat = fmt.fetch_meta_timeseries("CASH", "GBP", dt.date(2026, 9, 1), dt.date(2026, 9, 4))
    assert set(flat["Close"]) == {1.0}
    assert set(flat["Source"]) == {"cash"}

    monkeypatch.setattr(fmt, "is_valid_ticker", lambda t, e: True)
    monkeypatch.setattr(fmt, "fetch_with_price_source", lambda fetch, t, e, start, end: f"provider:{t}.{e}")
    assert fmt.fetch_meta_timeseries("CASH", "N", dt.date(2026, 9, 1), dt.date(2026, 9, 4)) == "provider:CASH.N"


def test_data_quality_checks_cash_stock_but_not_cash_balance():
    from backend.data_quality.issues import _parse_holding_ticker

    assert _parse_holding_ticker("CASH.N") == ("CASH", "N")
    assert _parse_holding_ticker("CASH.GBP") is None
    assert _parse_holding_ticker("GBP.CASH") is None


def test_query_prices_cash_stock_from_series(monkeypatch):
    from backend.routes import query

    monkeypatch.setattr(query, "_get_price_for_date_scaled", lambda sym, exch, on: (12.0, "Yahoo"))
    on = dt.date(2026, 10, 1)

    assert query._gbp_price("CASH.N", {}, on) == 12.0
    assert query._gbp_price("CASH.GBP", {}, on) == 1.0
    assert query._gbp_price("GBP.CASH", {}, on) == 1.0
    assert query._gbp_price("CASH.USD", {}, on) is None


def test_returns_and_reconciliation_include_cash_stock():
    from backend.common.ledger_performance import unreconciled_instruments
    from backend.common.position_returns import TOTAL_RETURN_FIELDS, attach_total_returns

    holdings = [{"ticker": "CASH.N", "units": 5}, {"ticker": "CASH.GBP", "units": 100}]
    assert unreconciled_instruments([], holdings, splits_for=lambda t: []) == ("CASH.N",)

    attach_total_returns(holdings, None, lambda ticker, keys: None)
    assert set(TOTAL_RETURN_FIELDS) <= holdings[0].keys()
    assert not set(TOTAL_RETURN_FIELDS) & holdings[1].keys()


@pytest.mark.parametrize(
    "ticker,resolved,expected",
    [
        # A bare CASH resolved to a market (default L, or CASH.N metadata) stays cash.
        ("CASH", ("CASH", "L"), ("CASH", "GBP")),
        ("CASH", ("CASH", "N"), ("CASH", "GBP")),
        ("CASH.USD", ("CASH", "L"), ("CASH", "USD")),
        ("CASH.GBP", ("CASH", "GBP"), ("CASH", "GBP")),
        ("GBP.CASH", ("GBP", "CASH"), ("GBP", "CASH")),
        ("CASH.N", ("CASH", "N"), ("CASH", "N")),
        ("VOD.L", ("VOD", "L"), ("VOD", "L")),
    ],
)
def test_cash_price_key_follows_the_stored_ticker(ticker, resolved, expected):
    assert cash_price_key(ticker, *resolved) == expected
