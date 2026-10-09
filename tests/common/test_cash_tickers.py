"""CASH as a cash balance vs CASH as a stock (Pathward Financial, CASH.N) (#10516)."""

import json

import pytest

from backend.common import instruments
from backend.common.cash_tickers import is_cash_ticker
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
