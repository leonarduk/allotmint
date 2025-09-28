import pytest
from fastapi import HTTPException

from backend.routes import opportunities as opportunities_module


@pytest.fixture(autouse=True)
def stub_weight_calculations(monkeypatch):
    monkeypatch.setattr(
        opportunities_module,
        "_calculate_weights_and_market_values",
        lambda *args, **kwargs: ([], {}, {}),
    )


@pytest.mark.asyncio
async def test_get_opportunities_rejects_invalid_days():
    with pytest.raises(HTTPException) as exc:
        await opportunities_module.get_opportunities(
            tickers="AAA",
            days=999,
            limit=5,
            min_weight=0.0,
            token=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid days"


@pytest.mark.asyncio
async def test_get_opportunities_rejects_group_and_tickers(monkeypatch):
    monkeypatch.setattr(opportunities_module.trading_agent, "run", lambda **_: [])
    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "top_movers",
        lambda *args, **kwargs: {"gainers": [], "losers": []},
    )

    with pytest.raises(HTTPException) as exc:
        await opportunities_module.get_opportunities(
            group="growth",
            tickers="AAA",
            days=1,
            limit=5,
            min_weight=0.0,
            token="token",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Specify either a group or tickers, but not both"


@pytest.mark.asyncio
async def test_group_requires_authentication():
    with pytest.raises(HTTPException) as exc:
        await opportunities_module.get_opportunities(
            group="growth",
            tickers=None,
            days=1,
            limit=5,
            min_weight=0.0,
            token=None,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_group_invalid_token(monkeypatch):
    monkeypatch.setattr(opportunities_module, "decode_token", lambda token: None)
    monkeypatch.setattr(opportunities_module.trading_agent, "run", lambda **_: [])
    monkeypatch.setattr(
        opportunities_module,
        "_group_opportunities",
        lambda *args, **kwargs: {"gainers": [], "losers": [], "anomalies": []},
    )

    with pytest.raises(HTTPException) as exc:
        await opportunities_module.get_opportunities(
            group="growth",
            tickers=None,
            days=1,
            limit=5,
            min_weight=0.0,
            token="token",
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authentication credentials"


@pytest.mark.asyncio
async def test_group_flow_populates_context_and_entries(monkeypatch):
    group_payload = {
        "gainers": [
            {
                "ticker": "AAA",
                "name": "Alpha",
                "change_pct": 1.5,
                "last_price_gbp": 101.0,
                "last_price_date": "2024-03-20",
                "market_value_gbp": 500.0,
            }
        ],
        "losers": [
            {
                "ticker": "BBB",
                "name": "Beta",
                "change_pct": -0.25,
                "last_price_gbp": 88.0,
                "last_price_date": "2024-03-20",
                "market_value_gbp": 300.0,
            },
            {
                "ticker": "CCC",
                "name": "Gamma",
                "change_pct": -3.0,
                "last_price_gbp": 44.0,
                "last_price_date": "2024-03-20",
                "market_value_gbp": 100.0,
            },
        ],
        "anomalies": ["BBB"],
    }
    monkeypatch.setattr(opportunities_module, "decode_token", lambda token: {"sub": "user"})
    monkeypatch.setattr(
        opportunities_module,
        "_group_opportunities",
        lambda *args, **kwargs: group_payload,
    )
    trading_signals = [
        {"ticker": "AAA", "action": "BUY", "reason": "Momentum"},
        {"ticker": "CCC", "action": "SELL", "reason": "Drawdown"},
    ]
    monkeypatch.setattr(
        opportunities_module.trading_agent, "run", lambda **_: trading_signals
    )

    response = await opportunities_module.get_opportunities(
        group="growth",
        tickers=None,
        days=1,
        limit=5,
        min_weight=0.0,
        token="token",
    )

    assert response.context.source == "group"
    assert response.context.group == "growth"
    assert response.context.days == 1
    assert response.context.anomalies == group_payload["anomalies"]
    assert [entry.ticker for entry in response.entries] == ["CCC", "AAA", "BBB"]
    assert response.entries[0].signal is not None
    assert response.entries[0].signal.ticker == "CCC"
    assert response.entries[1].signal is not None
    assert response.entries[1].signal.ticker == "AAA"
    assert response.entries[2].signal is None
    assert {signal.ticker for signal in response.signals} == {"AAA", "CCC"}


def test_group_opportunities_recalculates_weights_and_enriches(monkeypatch):
    summaries = [
        {"ticker": "AAA", "market_value_gbp": 200.0},
        {"ticker": "BBB", "market_value_gbp": 100.0},
        {"ticker": "CCC", "market_value_gbp": None},
    ]
    captured = {}

    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "instrument_summaries_for_group",
        lambda slug: summaries,
    )

    def fake_calculate(rows):
        captured["calculate_rows"] = rows
        return ["AAA", "BBB"], {"AAA": 50.0, "BBB": 50.0}, {"AAA": 120.0, "BBB": 80.0}

    monkeypatch.setattr(
        opportunities_module,
        "_calculate_weights_and_market_values",
        fake_calculate,
    )

    movers_payload = {"gainers": [{"ticker": "AAA"}], "losers": [{"ticker": "BBB"}], "anomalies": []}

    def fake_top_movers(tickers, days, limit, *, min_weight, weights):
        captured.update(
            {
                "tickers": tickers,
                "days": days,
                "limit": limit,
                "min_weight": min_weight,
                "weights": weights,
            }
        )
        return movers_payload

    monkeypatch.setattr(opportunities_module.instrument_api, "top_movers", fake_top_movers)

    def fake_enrich(movers, market_values):
        captured["enrich_args"] = (movers, market_values)
        return {"gainers": [], "losers": [], "anomalies": []}

    monkeypatch.setattr(
        opportunities_module,
        "_enrich_movers_with_market_values",
        fake_enrich,
    )

    result = opportunities_module._group_opportunities(
        "growth", days=5, limit=3, min_weight=2.5
    )

    assert captured["calculate_rows"] == summaries
    assert captured["tickers"] == ["AAA", "BBB"]
    assert captured["days"] == 5
    assert captured["limit"] == 3
    assert captured["min_weight"] == 2.5
    assert captured["weights"] == {
        "AAA": pytest.approx(200.0 / 300.0 * 100.0),
        "BBB": pytest.approx(100.0 / 300.0 * 100.0),
    }
    assert captured["enrich_args"] == (
        movers_payload,
        {"AAA": 120.0, "BBB": 80.0},
    )
    assert result == {"gainers": [], "losers": [], "anomalies": []}


def test_group_opportunities_error_and_short_circuit(monkeypatch):
    def raise_lookup(slug):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "instrument_summaries_for_group",
        raise_lookup,
    )

    with pytest.raises(HTTPException) as excinfo:
        opportunities_module._group_opportunities("growth", days=1, limit=5, min_weight=0.0)

    assert excinfo.value.status_code == 404

    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "instrument_summaries_for_group",
        lambda slug: [],
    )
    monkeypatch.setattr(
        opportunities_module,
        "_calculate_weights_and_market_values",
        lambda rows: ([], {}, {}),
    )

    def fail_top_movers(*args, **kwargs):
        raise AssertionError("should not call")

    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "top_movers",
        fail_top_movers,
    )

    result = opportunities_module._group_opportunities("growth", days=1, limit=5, min_weight=0.0)

    assert result == {"gainers": [], "losers": [], "anomalies": []}


@pytest.mark.asyncio
async def test_watchlist_blank_tickers(monkeypatch):
    monkeypatch.setattr(opportunities_module.trading_agent, "run", lambda **_: [])

    with pytest.raises(HTTPException) as exc:
        await opportunities_module.get_opportunities(
            group=None,
            tickers=" ,  , ",
            days=1,
            limit=5,
            min_weight=0.0,
            token=None,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "No tickers provided"


@pytest.mark.asyncio
async def test_watchlist_flow_sorted_and_enriched(monkeypatch):
    captured = {}
    watchlist_payload = {
        "gainers": [
            {"ticker": "bbb", "name": "Beta", "change_pct": 2.0},
            {"ticker": "AAA", "name": "Alpha", "change_pct": 0.5},
        ],
        "losers": [
            {"ticker": "CCC", "name": "Gamma", "change_pct": -3.5},
        ],
        "anomalies": ["XYZ"],
    }

    def fake_top_movers(tickers, days, limit, **kwargs):
        captured["tickers"] = tickers
        captured["days"] = days
        captured["limit"] = limit
        return watchlist_payload

    monkeypatch.setattr(
        opportunities_module.instrument_api,
        "top_movers",
        fake_top_movers,
    )
    trading_signals = [
        {"ticker": "BBB", "action": "BUY", "reason": "Watch"},
        {"ticker": "CCC", "action": "SELL", "reason": "Drop"},
    ]
    monkeypatch.setattr(
        opportunities_module.trading_agent, "run", lambda **_: trading_signals
    )

    response = await opportunities_module.get_opportunities(
        group=None,
        tickers=" AAA ,bbb , CCC ",
        days=7,
        limit=4,
        min_weight=0.0,
        token=None,
    )

    assert captured["tickers"] == ["AAA", "bbb", "CCC"]
    assert captured["days"] == 7
    assert captured["limit"] == 4
    assert response.context.source == "watchlist"
    assert response.context.tickers == ["AAA", "bbb", "CCC"]
    assert response.context.anomalies == watchlist_payload["anomalies"]
    assert [entry.ticker for entry in response.entries] == ["CCC", "bbb", "AAA"]
    assert response.entries[0].signal is not None and response.entries[0].signal.ticker == "CCC"
    assert response.entries[1].signal is not None and response.entries[1].signal.ticker == "BBB"
    assert response.entries[2].signal is None
