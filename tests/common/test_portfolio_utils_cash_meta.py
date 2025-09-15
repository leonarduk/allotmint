import pytest

from backend.common import portfolio_utils as pu


def test_canonicalise_cash_ticker():
    assert pu._canonicalise_cash_ticker("GBP.CASH") == "CASH.GBP"
    assert pu._canonicalise_cash_ticker("cash.gbp") == "CASH.GBP"


def test_currency_from_file_with_meta(monkeypatch):
    monkeypatch.setattr(pu, "_MISSING_META", set())
    monkeypatch.setattr(pu, "get_instrument_meta", lambda t: {"currency": "USD"})
    assert pu._currency_from_file("ABC.L") == "USD"


def test_currency_from_file_without_meta(monkeypatch):
    monkeypatch.setattr(pu, "_MISSING_META", set())
    monkeypatch.setattr(pu, "get_instrument_meta", lambda t: {})
    assert pu._currency_from_file("ABC.L") is None
