from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.routes import instrument


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_search_instruments_validation_and_trim(monkeypatch):
    monkeypatch.setattr(
        instrument,
        "list_instruments",
        lambda: [
            {
                "ticker": "DEV.L",
                "name": "Dev Plc",
                "sector": "Tech",
                "region": "UK",
            },
            {
                "ticker": "IGNORED",
                "name": "Other",
                "sector": "Finance",
                "region": "US",
            },
        ],
    )

    with pytest.raises(HTTPException):
        await instrument.search_instruments(q="   ")
    with pytest.raises(HTTPException):
        await instrument.search_instruments(q="foo", sector="   ", region=None)
    with pytest.raises(HTTPException):
        await instrument.search_instruments(q="foo", sector=None, region="   ")

    results = await instrument.search_instruments(
        q="  dev  ",
        sector="  TECH  ",
        region="  uk  ",
    )

    assert results == [
        {
            "ticker": "DEV.L",
            "name": "Dev Plc",
            "sector": "Tech",
            "region": "UK",
        }
    ]


def test_positions_for_ticker_cost_basis_fallback(monkeypatch):
    monkeypatch.setattr(
        instrument,
        "list_portfolios",
        lambda: [
            {
                "owner": "alex",
                "accounts": [
                    {
                        "account_type": "isa",
                        "holdings": [
                            {
                                "ticker": "ABC",
                                "units": 10,
                                "effective_cost_basis_gbp": 900,
                            }
                        ],
                    },
                    {
                        "account_type": "sipp",
                        "holdings": [
                            {
                                "ticker": "ABC",
                                "units": 5,
                                "cost_basis_gbp": 400,
                            }
                        ],
                    },
                ],
            },
            {
                "owner": "sam",
                "accounts": [
                    {
                        "account_type": "general",
                        "holdings": [
                            {
                                "ticker": "ABC",
                                "units": 2,
                                "cost_basis": "50",
                            },
                            {
                                "ticker": "IGNORED",
                                "units": 1,
                            },
                        ],
                    }
                ],
            },
        ],
    )

    positions = instrument._positions_for_ticker("ABC", last_close=100.0)

    assert len(positions) == 3
    assert positions[0]["market_value_gbp"] == 1000.0
    assert positions[0]["unrealised_gain_gbp"] == 100.0
    assert positions[1]["market_value_gbp"] == 500.0
    assert positions[1]["unrealised_gain_gbp"] == 100.0
    assert positions[2]["market_value_gbp"] == 200.0
    assert positions[2]["unrealised_gain_gbp"] == 150.0


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_instrument_empty_template(monkeypatch):
    monkeypatch.setattr(
        instrument,
        "load_meta_timeseries_range",
        lambda *_, **__: pd.DataFrame(columns=["Date", "Close"]),
    )
    monkeypatch.setattr(instrument, "get_security_meta", lambda _ticker: {"name": "Empty"})
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])

    response = await instrument.instrument(ticker="NONE.L", days=30, format="html", base_currency=None)

    assert response.status_code == 200
    assert "No price data" in response.body.decode()

    with pytest.raises(HTTPException) as exc:
        await instrument.instrument(ticker="NONE.L", days=30, format="json", base_currency=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_instrument_json_gbx_and_base_currency(monkeypatch):
    dates = pd.date_range(date(2024, 1, 1), periods=3, freq="D")
    df = pd.DataFrame({"Date": dates, "Close": [100.0, 110.0, 120.0]})

    monkeypatch.setattr(instrument, "load_meta_timeseries_range", lambda *_, **__: df)
    monkeypatch.setattr(
        instrument,
        "get_security_meta",
        lambda _ticker: {"name": "GBX Fund", "sector": "Growth", "currency": "GBX"},
    )
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])

    def fake_fetch(from_ccy, to_ccy, start, end):
        rng = pd.date_range(start, end, freq="D")
        return pd.DataFrame({"Date": rng, "Rate": [2.0] * len(rng)})

    monkeypatch.setattr(instrument, "fetch_fx_rate_range", fake_fetch)
    monkeypatch.setattr(instrument, "get_scaling_override", lambda *_, **__: 2.0)

    def fake_apply(df_in, scale):
        df_scaled = df_in.copy()
        if "Close" in df_scaled.columns:
            df_scaled["Close"] = pd.to_numeric(df_scaled["Close"], errors="coerce") * scale
        return df_scaled

    monkeypatch.setattr(instrument, "apply_scaling", fake_apply)
    monkeypatch.setattr(instrument.config, "base_currency", "USD")

    response = await instrument.instrument(
        ticker="GBX.L",
        days=30,
        format="json",
        base_currency="USD",
    )

    data = json.loads(response.body.decode())

    assert data["currency"] == "GBP"
    assert data["prices"][-1]["close"] == pytest.approx(240.0)
    assert data["prices"][-1]["close_gbp"] == pytest.approx(2.4)
    assert data["prices"][-1]["close_usd"] == pytest.approx(1.2)
    assert data["fx"] == {"USDGBP": "/timeseries/meta?ticker=USDGBP"}
    assert set(data["mini"]) == {"7", "30", "180"}


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_instrument_json_foreign_currency_fx(monkeypatch):
    dates = pd.date_range(date(2024, 2, 1), periods=2, freq="D")
    df = pd.DataFrame({"Date": dates, "Close": [10.0, 20.0]})

    monkeypatch.setattr(instrument, "load_meta_timeseries_range", lambda *_, **__: df)
    monkeypatch.setattr(
        instrument,
        "get_security_meta",
        lambda _ticker: {"name": "EUR Fund", "sector": "Value", "currency": "EUR"},
    )
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])

    def fake_fetch(from_ccy, to_ccy, start, end):
        rng = pd.date_range(start, end, freq="D")
        rate = 0.8 if from_ccy == "EUR" else 1.25
        return pd.DataFrame({"Date": rng, "Rate": [rate] * len(rng)})

    monkeypatch.setattr(instrument, "fetch_fx_rate_range", fake_fetch)
    monkeypatch.setattr(instrument, "get_scaling_override", lambda *_, **__: 1.0)
    monkeypatch.setattr(instrument, "apply_scaling", lambda df_in, _scale: df_in)
    monkeypatch.setattr(instrument.config, "base_currency", "GBP")

    response = await instrument.instrument(
        ticker="EUR.PA",
        days=180,
        format="json",
        base_currency="GBP",
    )

    data = json.loads(response.body.decode())
    assert data["currency"] == "GBP"
    assert data["prices"][0]["close_gbp"] == pytest.approx(8.0)
    assert data["fx"] == {"EURGBP": "/timeseries/meta?ticker=EURGBP"}


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_instrument_json_scales_positions(monkeypatch):
    dates = pd.date_range(date(2024, 3, 1), periods=2, freq="D")
    df = pd.DataFrame(
        {
            "Date": dates,
            "Close": [10.0, 12.0],
            "Close_gbp": [9.0, 11.0],
        }
    )

    monkeypatch.setattr(instrument, "load_meta_timeseries_range", lambda *_, **__: df)
    monkeypatch.setattr(
        instrument,
        "get_security_meta",
        lambda _ticker: {"name": "Scale Fund", "currency": "GBP"},
    )

    captured_last_close: dict[str, float | None] = {}

    positions = [
        {
            "owner": "alex",
            "account": "isa",
            "units": 10,
            "market_value_gbp": 100.0,
            "unrealised_gain_gbp": 5.0,
            "gain_pct": 5.0,
        },
        {
            "owner": "sam",
            "account": "general",
            "units": 2,
            "market_value_gbp": 20.0,
            "unrealised_gain_gbp": None,
            "gain_pct": None,
        },
    ]

    def fake_positions(ticker: str, last_close: float | None):
        captured_last_close["value"] = last_close
        return positions

    monkeypatch.setattr(instrument, "_positions_for_ticker", fake_positions)
    monkeypatch.setattr(instrument, "get_scaling_override", lambda *a, **k: 2.0)
    monkeypatch.setattr(instrument, "apply_scaling", lambda df_in, scale: df_in)
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])

    response = await instrument.instrument(
        ticker="ABC.L",
        days=30,
        format="json",
        base_currency="GBP",
    )

    payload = json.loads(response.body.decode())

    assert captured_last_close["value"] == pytest.approx(22.0)
    assert payload["positions"][0]["unrealised_gain_gbp"] == pytest.approx(10.0)
    assert payload["positions"][1]["unrealised_gain_gbp"] is None

async def test_intraday_returns_prices(monkeypatch):
    timestamps = pd.date_range("2024-03-01", periods=2, freq="5min")
    df = pd.DataFrame({"Close": [101.5, 102.75]}, index=timestamps)
    df.index.name = "Datetime"

    class DummyTicker:
        def history(self, period: str, interval: str):
            assert period == "2d"
            assert interval == "5m"
            return df

    monkeypatch.setattr(instrument.yf, "Ticker", lambda _symbol: DummyTicker())

    result = await instrument.intraday("AAA.L")

    assert result["ticker"] == "AAA.L"
    assert len(result["prices"]) == 2
    assert result["prices"][0]["timestamp"] == timestamps[0].isoformat()
    assert isinstance(result["prices"][0]["close"], float)
    assert result["prices"][0]["close"] == pytest.approx(101.5)
    assert result["prices"][1]["timestamp"] == timestamps[1].isoformat()
    assert isinstance(result["prices"][1]["close"], float)
    assert result["prices"][1]["close"] == pytest.approx(102.75)


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_intraday_no_data(monkeypatch):
    class EmptyTicker:
        def history(self, period: str, interval: str):
            assert period == "2d"
            assert interval == "5m"
            empty = pd.DataFrame(columns=["Close"])
            empty.index.name = "Datetime"
            return empty

    monkeypatch.setattr(instrument.yf, "Ticker", lambda _symbol: EmptyTicker())

    with pytest.raises(HTTPException) as exc:
        await instrument.intraday("AAA.L")

    assert exc.value.status_code == 404
    assert exc.value.detail == "no intraday data"

