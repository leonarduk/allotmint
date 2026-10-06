"""Dated (``as_of``) holding valuation must not use today's snapshot price (#9834)."""

import datetime as dt

import pandas as pd
import pytest

import backend.common.portfolio_utils as pu
from backend.common import holding_utils as hu
from backend.common.constants import ACQUIRED_DATE, COST_BASIS_GBP, TICKER, UNITS
from backend.utils.pricing_dates import PricingDateCalculator

AS_OF = dt.date(2008, 9, 15)
TODAY = dt.date(2026, 10, 6)


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {"currency": "GBP"})
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    calls = []

    def dated_price(ticker, exchange, d, field="Close_gbp"):
        calls.append(d)
        return None, None, None

    monkeypatch.setattr(hu, "_get_dated_price_for_date_scaled", dated_price)
    return calls


def _enrich(calc):
    holding = {TICKER: "FOO.L", UNITS: 10, COST_BASIS_GBP: 0.0, ACQUIRED_DATE: "2020-01-01"}
    return hu.enrich_holding(holding, TODAY, price_cache={}, calc=calc)


def _own_price(monkeypatch, price):
    monkeypatch.setattr(
        hu,
        "_get_dated_price_for_date_scaled",
        lambda ticker, exchange, d, field="Close_gbp": (price, "Yahoo", d),
    )


def test_has_explicit_reporting_date():
    assert PricingDateCalculator(reporting_date=AS_OF).has_explicit_reporting_date
    assert not PricingDateCalculator(today=TODAY).has_explicit_reporting_date


def test_snapshot_dated_after_as_of_is_ignored(monkeypatch, stubs):
    pu._PRICE_SNAPSHOT["FOO.L"] = {"last_price": 99.0, "last_price_date": "2026-10-05"}
    _own_price(monkeypatch, 40.0)

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert result["price"] == pytest.approx(40.0)
    assert result["latest_source"] == "Yahoo"
    assert result["market_value_gbp"] == pytest.approx(400.0)


def test_undated_snapshot_is_ignored_for_explicit_date(monkeypatch, stubs):
    pu._PRICE_SNAPSHOT["FOO.L"] = {"last_price": 99.0, "is_stale": False}
    _own_price(monkeypatch, 40.0)

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert result["price"] == pytest.approx(40.0)


def test_snapshot_dated_on_as_of_is_used(stubs):
    pu._PRICE_SNAPSHOT["FOO.L"] = {"last_price": 99.0, "last_price_date": AS_OF.isoformat()}

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert result["price"] == pytest.approx(99.0)
    assert result["latest_source"] == "snapshot"


def test_snapshot_still_used_without_explicit_date(stubs):
    pu._PRICE_SNAPSHOT["FOO.L"] = {"last_price": 99.0, "is_stale": False}

    result = _enrich(PricingDateCalculator(today=TODAY))

    assert result["price"] == pytest.approx(99.0)
    assert result["latest_source"] == "snapshot"


def test_proxy_prices_holding_before_its_own_history(monkeypatch, stubs):
    requested = []

    def proxied(ticker, start, end):
        requested.append((ticker, start, end))
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2008-09-12", "2008-09-15"]),
                "Close_gbp": [21.0, 20.0],
                "Source": ["proxy:IGLT.L", "proxy:IGLT.L"],
            }
        )

    monkeypatch.setattr(hu, "proxied_daily_history", proxied)

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert requested == [("FOO.L", AS_OF - dt.timedelta(days=7), AS_OF)]
    assert result["price"] == pytest.approx(20.0)
    assert result["latest_source"] == "proxy:IGLT.L"
    assert result["is_stale"] is True
    assert result["market_value_gbp"] == pytest.approx(200.0)


def test_own_rows_from_proxy_resolver_are_not_used(monkeypatch, stubs):
    frame = pd.DataFrame({"Date": pd.to_datetime([AS_OF]), "Close_gbp": [5.0], "Source": ["own"]})
    monkeypatch.setattr(hu, "proxied_daily_history", lambda *_: frame)

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert result["price"] is None
    assert result["market_value_gbp"] is None


def test_no_own_or_proxy_history_stays_unpriced(monkeypatch, stubs):
    empty = pd.DataFrame(columns=["Date", "Close_gbp", "Source"])
    monkeypatch.setattr(hu, "proxied_daily_history", lambda *_: empty)

    result = _enrich(PricingDateCalculator(reporting_date=AS_OF))

    assert result["price"] is None
    assert result["market_value_gbp"] is None


def test_proxy_not_consulted_without_explicit_date(monkeypatch, stubs):
    def fail(*_):
        raise AssertionError("proxy lookup must only run for an explicit date")

    monkeypatch.setattr(hu, "proxied_daily_history", fail)

    result = _enrich(PricingDateCalculator(today=TODAY))

    assert result["price"] is None
