"""Unit tests for the Opportunities FastAPI handler."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.routes import opportunities


@pytest.mark.asyncio
async def test_get_opportunities_rejects_invalid_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handler should reject unsupported lookback windows."""

    monkeypatch.setattr(opportunities.instrument_api, "top_movers", lambda *_, **__: {})
    monkeypatch.setattr(opportunities, "_group_opportunities", lambda *_, **__: {})
    monkeypatch.setattr(
        opportunities,
        "_calculate_weights_and_market_values",
        lambda *_, **__: ([], {}, {}),
    )
    monkeypatch.setattr(opportunities.trading_agent, "run", lambda **__: [])
    monkeypatch.setattr(opportunities, "decode_token", lambda token: {"sub": "user"})

    with pytest.raises(HTTPException) as exc:
        await opportunities.get_opportunities(
            group="growth",
            tickers=None,
            days=999,
            token="token",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid days"


@pytest.mark.asyncio
async def test_get_opportunities_rejects_group_and_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supplying both a group slug and tickers should fail validation."""

    monkeypatch.setattr(opportunities.instrument_api, "top_movers", lambda *_, **__: {})
    monkeypatch.setattr(opportunities, "_group_opportunities", lambda *_, **__: {})
    monkeypatch.setattr(
        opportunities,
        "_calculate_weights_and_market_values",
        lambda *_, **__: ([], {}, {}),
    )
    monkeypatch.setattr(opportunities.trading_agent, "run", lambda **__: [])
    monkeypatch.setattr(opportunities, "decode_token", lambda token: {"sub": "user"})

    with pytest.raises(HTTPException) as exc:
        await opportunities.get_opportunities(
            group="growth",
            tickers="AAA,BBB",
            days=1,
            token="token",
        )

    assert exc.value.status_code == 400
    assert "Specify either a group or tickers" in exc.value.detail


@pytest.mark.asyncio
async def test_get_opportunities_group_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the group path including authentication and enrichment."""

    monkeypatch.setattr(opportunities.instrument_api, "top_movers", lambda *_, **__: {})
    monkeypatch.setattr(
        opportunities,
        "_calculate_weights_and_market_values",
        lambda *_, **__: ([], {}, {}),
    )
    monkeypatch.setattr(
        opportunities.trading_agent,
        "run",
        lambda **__: [
            {"ticker": "AAA", "action": "BUY", "reason": "Alpha rising"},
            {"ticker": "BBB", "action": "SELL", "reason": "Beta falling"},
        ],
    )

    group_payload = {
        "gainers": [
            {
                "ticker": "AAA",
                "name": "Alpha",
                "change_pct": 2.0,
                "last_price_gbp": 15.0,
                "last_price_date": "2024-01-01",
                "market_value_gbp": 150.0,
            }
        ],
        "losers": [
            {
                "ticker": "BBB",
                "name": "Beta",
                "change_pct": -4.0,
                "last_price_gbp": 5.0,
                "last_price_date": "2024-01-02",
                "market_value_gbp": 50.0,
            }
        ],
        "anomalies": ["BBB data gap"],
    }
    monkeypatch.setattr(opportunities, "_group_opportunities", lambda *_, **__: group_payload)

    monkeypatch.setattr(opportunities, "decode_token", lambda token: None)
    with pytest.raises(HTTPException) as exc_invalid:
        await opportunities.get_opportunities(
            group="growth",
            tickers=None,
            days=1,
            token="token",
        )

    assert exc_invalid.value.status_code == 401
    assert exc_invalid.value.detail == "Invalid authentication credentials"

    monkeypatch.setattr(opportunities, "decode_token", lambda token: {"sub": "user"})
    response = await opportunities.get_opportunities(
        group="growth",
        tickers=None,
        days=1,
        token="token",
    )

    assert response.context.source == "group"
    assert response.context.group == "growth"
    assert response.context.days == 1
    assert response.context.anomalies == ["BBB data gap"]

    tickers = [entry.ticker for entry in response.entries]
    assert tickers == ["BBB", "AAA"]
    assert response.entries[0].signal and response.entries[0].signal.action == "SELL"
    assert response.entries[1].signal and response.entries[1].signal.action == "BUY"
    assert response.entries[0].market_value_gbp == 50.0
    assert response.entries[1].last_price_gbp == 15.0


@pytest.mark.asyncio
async def test_get_opportunities_watchlist_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Watchlist requests should validate inputs and merge trading data."""

    monkeypatch.setattr(
        opportunities.trading_agent,
        "run",
        lambda **__: [
            {"ticker": "AAA", "action": "BUY", "reason": "Alpha rising"},
            {"ticker": "BBB", "action": "SELL", "reason": "Beta falling"},
        ],
    )
    monkeypatch.setattr(opportunities, "_group_opportunities", lambda *_, **__: {})
    monkeypatch.setattr(
        opportunities,
        "_calculate_weights_and_market_values",
        lambda *_, **__: ([], {}, {}),
    )

    captured: dict[str, object] = {}

    def fake_top_movers(tickers, days, limit, **kwargs):
        captured["tickers"] = tickers
        captured["days"] = days
        captured["limit"] = limit
        return {
            "gainers": [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "change_pct": 2.0,
                    "last_price_gbp": 10.5,
                    "last_price_date": "2024-01-03",
                    "market_value_gbp": 100.0,
                },
                {
                    "ticker": "CCC",
                    "name": "Gamma",
                    "change_pct": 0.5,
                    "last_price_gbp": 30.0,
                    "last_price_date": "2024-01-04",
                    "market_value_gbp": 300.0,
                },
            ],
            "losers": [
                {
                    "ticker": "BBB",
                    "name": "Beta",
                    "change_pct": -4.0,
                    "last_price_gbp": 20.0,
                    "last_price_date": "2024-01-05",
                    "market_value_gbp": 200.0,
                }
            ],
            "anomalies": ["BBB flagged"],
        }

    monkeypatch.setattr(opportunities.instrument_api, "top_movers", fake_top_movers)
    monkeypatch.setattr(opportunities, "decode_token", lambda token: {"sub": "user"})

    with pytest.raises(HTTPException) as exc_blank:
        await opportunities.get_opportunities(group=None, tickers=" , ", days=1)

    assert exc_blank.value.status_code == 400
    assert exc_blank.value.detail == "No tickers provided"

    response = await opportunities.get_opportunities(
        group=None,
        tickers=" AAA ,BBB , , CCC ",
        days=7,
        limit=3,
    )

    assert captured["tickers"] == ["AAA", "BBB", "CCC"]
    assert captured["days"] == 7
    assert captured["limit"] == 3

    assert response.context.source == "watchlist"
    assert response.context.tickers == ["AAA", "BBB", "CCC"]
    assert response.context.anomalies == ["BBB flagged"]

    tickers = [entry.ticker for entry in response.entries]
    assert tickers == ["BBB", "AAA", "CCC"]

    first_entry = response.entries[0]
    assert first_entry.signal and first_entry.signal.action == "SELL"
    assert first_entry.last_price_gbp == 20.0
    assert first_entry.market_value_gbp == 200.0

    second_entry = response.entries[1]
    assert second_entry.signal and second_entry.signal.action == "BUY"
    assert second_entry.last_price_date == "2024-01-03"

    third_entry = response.entries[2]
    assert third_entry.signal is None
    assert third_entry.market_value_gbp == 300.0

    assert response.signals and len(response.signals) == 2
