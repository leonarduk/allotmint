import pytest
import backend.common.portfolio_utils as portfolio_utils
from backend.common import instrument_api as ia


def _fake_fx(rates: dict):
    """Return a fetch_fx_rate_range mock that returns per-currency rates.

    ``rates`` maps currency code (uppercase) to the GBP rate for that currency,
    e.g. {"USD": 0.8} means 1 USD = 0.8 GBP.
    """

    def _fetch(base: str, quote: str, start, end):
        import pandas as pd

        rate = rates.get(base.upper(), 1.0)
        return pd.DataFrame({"Date": [start], "Rate": [rate]})

    return _fetch


def test_currency_from_instrument_meta(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 1}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: {"currency": "USD"})
    monkeypatch.setenv("TESTING", "1")

    rows = portfolio_utils.aggregate_by_ticker(portfolio)

    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"


def test_aggregate_by_ticker_fx_conversion(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "ABC",
                        "units": 1,
                        "market_value_gbp": 100,
                        "gain_gbp": 10,
                        "cost_gbp": 90,
                    }
                ]
            }
        ]
    }

    # Explicitly empty snapshot so this test is hermetic regardless of run order.
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: {"currency": "USD"})
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _fake_fx({"USD": 0.8, "EUR": 0.9}))

    rows_usd = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="USD")
    assert len(rows_usd) == 1
    rate_usd = 1 / 0.8
    assert rows_usd[0]["market_value_gbp"] == round(100 * rate_usd, 2)
    assert rows_usd[0]["gain_gbp"] == round(10 * rate_usd, 2)
    assert rows_usd[0]["cost_gbp"] == round(90 * rate_usd, 2)
    assert rows_usd[0]["last_price_gbp"] == pytest.approx(100 * rate_usd, rel=1e-4)
    assert rows_usd[0]["market_value_currency"] == "USD"

    rows_eur = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="EUR")
    assert len(rows_eur) == 1
    rate_eur = 1 / 0.9
    assert rows_eur[0]["market_value_gbp"] == round(100 * rate_eur, 2)
    assert rows_eur[0]["gain_gbp"] == round(10 * rate_eur, 2)
    assert rows_eur[0]["cost_gbp"] == round(90 * rate_eur, 2)
    assert rows_eur[0]["last_price_gbp"] == pytest.approx(100 * rate_eur, rel=1e-4)
    assert rows_eur[0]["market_value_currency"] == "EUR"


def test_aggregate_by_ticker_snapshot_price_is_fx_converted(monkeypatch):
    """Exercises the fallback path: no price_currency in snapshot, falls back to
    row currency from instrument metadata."""
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 2.0, "cost_gbp": 0.0}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _t: {"currency": "USD"})
    # USD rate: 0.8 means 1 USD = 0.8 GBP.  Mock differentiates by currency so
    # the test would fail if the rate direction were inverted.
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _fake_fx({"USD": 0.8}))
    # No price_currency in snapshot -> falls back to row.get("currency") from metadata
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"ABC.L": {"last_price": 100.0}})

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert len(rows) == 1
    # 2 units * 100 USD * 0.8 (USD->GBP) = 160 GBP
    assert rows[0]["market_value_gbp"] == 160.0
    assert rows[0]["last_price_gbp"] == pytest.approx(80.0)


def test_aggregate_by_ticker_snapshot_price_currency_field(monkeypatch):
    """Exercises the primary path: price_currency is present in the snapshot dict.
    This tests snap.get("price_currency") directly rather than the metadata fallback."""
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 5.0, "cost_gbp": 0.0}]}]}

    # USD rate: 0.8.  Mock differentiates so inverted rate would fail.
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _fake_fx({"USD": 0.8}))
    # price_currency explicitly set in snapshot -> primary path, metadata not needed
    monkeypatch.setattr(
        portfolio_utils,
        "_PRICE_SNAPSHOT",
        {"ABC.L": {"last_price": 50.0, "price_currency": "USD"}},
    )
    # Instrument metadata has no currency — confirms price_currency from snapshot is used
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _t: {})

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert len(rows) == 1
    # 5 units * 50 USD * 0.8 (USD->GBP) = 200 GBP
    assert rows[0]["market_value_gbp"] == pytest.approx(200.0)
    assert rows[0]["last_price_gbp"] == pytest.approx(40.0)


def test_aggregate_by_ticker_snapshot_price_handles_gbpence(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC.L", "units": 10.0, "cost_gbp": 0.0}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _t: {"currency": "GBp"})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"ABC.L": {"last_price": 250.0}})
    # GBX->GBP short-circuits in _fx_to_base (same currency after conversion),
    # but patch defensively to prevent any live network call.
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _fake_fx({"GBP": 1.0}))

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert len(rows) == 1
    # 250 pence = £2.50; 10 units * £2.50 = £25.00
    assert rows[0]["last_price_gbp"] == pytest.approx(2.5)
    assert rows[0]["market_value_gbp"] == 25.0


def test_aggregate_by_ticker_snapshot_price_uses_direct_native_to_base_fx(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 2.0, "cost_gbp": 100.0}]}]}

    monkeypatch.setattr(
        portfolio_utils,
        "_PRICE_SNAPSHOT",
        {"ABC.L": {"last_price": 50.0, "price_currency": "USD"}},
    )
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _t: {"currency": "USD"})

    def _fake_fx_to_base(from_ccy, to_ccy, _cache=None):
        pair = (str(from_ccy).upper(), str(to_ccy).upper())
        rates = {
            ("USD", "GBP"): 0.8,
            ("GBP", "USD"): 1.25,
            ("USD", "USD"): 1.0,
        }
        return rates.get(pair, 1.0)

    monkeypatch.setattr(portfolio_utils, "_fx_to_base", _fake_fx_to_base)

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="USD")
    assert len(rows) == 1

    # Direct USD->USD conversion should keep the snapshot price at 50.0 per unit
    # and avoid a two-step USD->GBP->USD recalculation.
    assert rows[0]["last_price_gbp"] == pytest.approx(50.0)
    assert rows[0]["market_value_gbp"] == pytest.approx(100.0)
    # Cost basis still comes from GBP-native holdings and should be converted once.
    assert rows[0]["cost_gbp"] == pytest.approx(125.0)
    assert rows[0]["gain_gbp"] == pytest.approx(-25.0)


def test_aggregate_by_ticker_snapshot_price_keeps_gbp(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC.L", "units": 10.0, "cost_gbp": 0.0}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda _t: {"currency": "GBP"})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"ABC.L": {"last_price": 250.0}})
    # GBP->GBP short-circuits, but patch defensively.
    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", _fake_fx({"GBP": 1.0}))

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="GBP")
    assert len(rows) == 1
    assert rows[0]["last_price_gbp"] == pytest.approx(250.0)
    assert rows[0]["market_value_gbp"] == 2500.0


def test_aggregate_by_ticker_sets_grouping(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA.L", "units": 1.0, "market_value_gbp": 100.0, "gain_gbp": 10.0},
                    {"ticker": "BBB.L", "units": 2.0, "market_value_gbp": 50.0, "gain_gbp": 5.0},
                    {"ticker": "CCC.L", "units": 3.0, "market_value_gbp": 25.0, "gain_gbp": 2.5},
                ]
            }
        ]
    }

    meta = {
        "AAA.L": {"name": "Alpha", "currency": "GBP", "grouping": "Explicit"},
        "BBB.L": {"name": "Beta", "currency": "GBP", "sector": "Sector B"},
        "CCC.L": {"name": "Gamma", "currency": "GBP", "region": "Region C"},
    }

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: meta.get(t, {}))
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda t: meta.get(t, {}))
    monkeypatch.setattr(ia, "price_change_pct", lambda ticker, days: None)

    rows = portfolio_utils.aggregate_by_ticker(portfolio)
    assert len(rows) == 3
    by_ticker = {row["ticker"]: row for row in rows}

    assert by_ticker["AAA.L"]["grouping"] == "Explicit"
    assert by_ticker["BBB.L"]["grouping"] == "Sector B"
    assert by_ticker["CCC.L"]["grouping"] == "Region C"


def test_normalize_currency_code_logs_when_missing(caplog):
    with caplog.at_level("WARNING", logger="portfolio_utils"):
        normalized = portfolio_utils._normalize_currency_code(None)

    assert normalized == "GBP"
    assert (
        "_normalize_currency_code received empty/missing currency; defaulting to GBP."
        in caplog.text
    )
