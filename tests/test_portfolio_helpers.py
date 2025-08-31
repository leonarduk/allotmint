import pytest

from backend.routes import portfolio


def test_calculate_weights_and_market_values():
    summaries = [
        {"ticker": "aaa", "market_value_gbp": 100.0},
        {"ticker": "BBB.L", "market_value_gbp": 50.0},
        {"ticker": None, "market_value_gbp": 10.0},
    ]
    tickers, weights, market_values = portfolio._calculate_weights_and_market_values(summaries)

    assert tickers == ["aaa", "BBB.L"]
    assert weights == {"aaa": pytest.approx(50.0), "BBB.L": pytest.approx(50.0)}
    assert market_values["AAA"] == 100.0
    assert market_values["BBB"] == 50.0
    assert market_values["BBB.L"] == 50.0


def test_enrich_movers_with_market_values():
    movers = {
        "gainers": [{"ticker": "AAA"}, {"ticker": "BBB.L"}],
        "losers": [{"ticker": "CCC"}],
    }
    market_values = {"AAA": 100.0, "BBB": 50.0, "BBB.L": 50.0, "CCC": 25.0}
    enriched = portfolio._enrich_movers_with_market_values(movers, market_values)

    assert enriched["gainers"][0]["market_value_gbp"] == 100.0
    assert enriched["gainers"][1]["market_value_gbp"] == 50.0
    assert enriched["losers"][0]["market_value_gbp"] == 25.0
