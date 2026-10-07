from typing import Any

import pytest
import requests

from backend.common import morningstar

ROWS = [
    {"SecId": "0P0000HYBM", "isin": "JE00B1VS3770", "ExchangeId": "EX$$$$XAMS", "Currency": "EUR"},
    {"SecId": "0P00008UKW", "isin": "JE00B1VS3770", "ExchangeId": "EX$$$$XLON", "Currency": "USD"},
    {"SecId": "0P0000AATZ", "isin": "JE00B1VS3770", "ExchangeId": "EX$$$$XLON", "Currency": "GBP"},
    {"SecId": "0P0000N8R2", "isin": "JE00B1VS3770", "ExchangeId": "EX$$$$$$$$", "Currency": "GBP"},
]


def test_select_prefers_exchange_and_currency_match():
    assert morningstar.select_sec_id(ROWS, "L", "GBP") == "0P0000AATZ"
    assert morningstar.select_sec_id(ROWS, "L", "USD") == "0P00008UKW"


def test_select_treats_pence_as_sterling():
    assert morningstar.select_sec_id(ROWS, "L", "GBX") == "0P0000AATZ"


def test_select_never_guesses_another_currency_line():
    assert morningstar.select_sec_id(ROWS, "L", "JPY") is None


def test_select_without_currency_needs_a_single_listing():
    assert morningstar.select_sec_id(ROWS, "L", None) is None
    assert morningstar.select_sec_id(ROWS, "AS", None) == "0P0000HYBM"


def test_select_ignores_malformed_exchange_ids():
    rows = [{"SecId": "0P0000BAD1", "ExchangeId": "LON", "Currency": "GBP"}, {"SecId": "0P0000BAD2"}]
    assert morningstar.select_sec_id(rows, "L", "GBP") is None


def test_select_returns_none_without_a_listing_on_the_exchange():
    assert morningstar.select_sec_id(ROWS, "N", "USD") is None
    assert morningstar.select_sec_id(ROWS, "XX", "GBP") is None


@pytest.fixture(autouse=True)
def _clear_unresolved_cache():
    morningstar._UNRESOLVED.clear()
    yield
    morningstar._UNRESOLVED.clear()


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def test_resolve_ignores_rows_for_other_isins(monkeypatch):
    other = {"SecId": "0P0000ZZZZ", "isin": "GB0000000000", "ExchangeId": "EX$$$$XLON", "Currency": "GBP"}
    calls: list[dict] = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return _Response({"rows": [other, *ROWS]})

    monkeypatch.setattr(morningstar.requests, "get", fake_get)
    assert morningstar.resolve_sec_id("JE00B1VS3770", "L", "GBX") == "0P0000AATZ"
    assert calls[0]["term"] == "JE00B1VS3770"


def test_resolve_returns_none_on_network_error(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(morningstar.requests, "get", fake_get)
    assert morningstar.resolve_sec_id("JE00B1VS3770", "L", "GBP") is None


def test_resolve_remembers_unresolvable_listings(monkeypatch):
    calls: list[dict] = []

    def fake_get(url, params, timeout):
        calls.append(params)
        return _Response({"rows": ROWS})

    monkeypatch.setattr(morningstar.requests, "get", fake_get)
    assert morningstar.resolve_sec_id("JE00B1VS3770", "N", "USD") is None
    assert morningstar.resolve_sec_id("JE00B1VS3770", "N", "USD") is None
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{}, {"rows": None}, {"rows": "nope"}])
def test_resolve_handles_unexpected_payloads(monkeypatch, payload):
    monkeypatch.setattr(morningstar.requests, "get", lambda *a, **k: _Response(payload))
    assert morningstar.resolve_sec_id("JE00B1VS3770", "L", "GBP") is None
