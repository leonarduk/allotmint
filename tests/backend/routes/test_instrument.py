from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.routes import instrument


def _auth_client(app: FastAPI) -> TestClient:
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


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


@pytest.mark.asyncio
@pytest.mark.anyio("asyncio")
async def test_instrument_last_close_fx_conversion(monkeypatch):
    dates = pd.date_range(date(2024, 4, 1), periods=3, freq="D")
    df = pd.DataFrame({"Date": dates, "Close": [15.5, 16.75, 17.25]})

    monkeypatch.setattr(instrument, "load_meta_timeseries_range", lambda *_, **__: df)
    monkeypatch.setattr(
        instrument,
        "get_security_meta",
        lambda _ticker: {"name": "US Fund", "currency": "USD"},
    )
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])
    monkeypatch.setattr(instrument, "get_scaling_override", lambda *_, **__: 1.0)
    monkeypatch.setattr(instrument, "apply_scaling", lambda df_in, _scale: df_in)

    captured_last_close: dict[str, float | None] = {}
    fx_call: dict[str, tuple[str, str, date, date]] = {}

    def fake_positions(ticker: str, last_close: float | None):
        captured_last_close["value"] = last_close
        return []

    def fake_fetch_fx_rate_range(from_ccy, to_ccy, start, end):
        if start != end:
            return pd.DataFrame(columns=["Date", "Rate"])
        fx_call["args"] = (from_ccy, to_ccy, start, end)
        rng = pd.date_range(start, end, freq="D")
        return pd.DataFrame({"Date": rng, "Rate": [0.78] * len(rng)})

    monkeypatch.setattr(instrument, "_positions_for_ticker", fake_positions)
    monkeypatch.setattr(instrument, "fetch_fx_rate_range", fake_fetch_fx_rate_range)

    response = await instrument.instrument(
        ticker="USD.FUND",
        days=30,
        format="json",
        base_currency="GBP",
    )

    assert response.status_code == 200
    assert captured_last_close["value"] == pytest.approx(17.25 * 0.78)
    assert fx_call["args"] == ("USD", "GBP", dates[-1].date(), dates[-1].date())


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
    detail = exc.value.detail
    assert isinstance(detail, str)
    lowered = detail.lower()
    assert "no intraday data" in lowered
    assert "aaa.l" in lowered


def test_instrument_search_truncates_at_maximum(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True, raising=False)
    app = create_app()

    def fake_list_instruments():
        for idx in range(25):
            yield {
                "ticker": f"TRIM{idx:02d}.L",
                "name": f"Trim Candidate {idx}",
                "sector": "Technology",
                "region": "UK",
            }

    monkeypatch.setattr(instrument, "list_instruments", fake_list_instruments)

    client = _auth_client(app)
    response = client.get("/instrument/search", params={"q": "trim"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 20
    assert payload[0]["ticker"] == "TRIM00.L"
    assert payload[-1]["ticker"] == "TRIM19.L"


def test_instrument_json_days_zero_uses_epoch_and_usd_branch(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True, raising=False)
    monkeypatch.setattr(config, "base_currency", "USD", raising=False)
    app = create_app()
    monkeypatch.setattr(instrument.config, "base_currency", "USD", raising=False)

    captured: dict[str, object] = {}

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    df = pd.DataFrame({"Date": dates, "Close_gbp": [1.1, 1.2, 1.3]})

    def fake_load(tkr, exch, start_date, end_date):
        captured["ticker"] = tkr
        captured["exchange"] = exch
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return df.copy()

    def fake_fx(from_ccy, to_ccy, start, end):
        if from_ccy == "USD" and to_ccy == "GBP":
            rng = pd.date_range(start, end, freq="D")
            return pd.DataFrame({"Date": rng, "Rate": [0.8] * len(rng)})
        return pd.DataFrame(columns=["Date", "Rate"])

    monkeypatch.setattr(instrument, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(instrument, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(instrument, "get_security_meta", lambda _t: {"name": "Epoch", "currency": "GBP"})
    monkeypatch.setattr(instrument, "list_portfolios", lambda: [])
    monkeypatch.setattr(instrument, "get_scaling_override", lambda *a, **k: 1.0)

    client = _auth_client(app)
    response = client.get(
        "/instrument",
        params={
            "ticker": "EPOCH.L",
            "days": 0,
            "format": "json",
            "base_currency": "GBP",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert captured["start_date"] == date(1900, 1, 1)
    assert payload["from"] == "1900-01-01"
    assert len(payload["prices"]) == 3

    last = payload["prices"][-1]
    assert last["close"] == pytest.approx(1.3)
    assert last["close_gbp"] == pytest.approx(1.3)
    assert "close_usd" in last
    assert last["close_usd"] == pytest.approx(last["close_gbp"] / 0.8)


def test_intraday_returns_502_on_provider_error(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True, raising=False)
    app = create_app()

    def raising_ticker(_symbol):
        raise RuntimeError("upstream failure")

    monkeypatch.setattr(instrument.yf, "Ticker", raising_ticker)

    client = _auth_client(app)
    response = client.get("/instrument/intraday", params={"ticker": "ERR.L"})

    assert response.status_code == 502
    assert "upstream failure" in response.text

