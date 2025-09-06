import backend.common.prices as prices
from backend.utils.scenario_tester import apply_historical_event, apply_price_shock


def test_price_shock_uses_cached_price_for_missing_current_price(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "ABC.L",
                        "units": 10,
                        "market_value_gbp": 0.0,
                    }
                ],
                "value_estimate_gbp": 0.0,
            }
        ],
        "total_value_estimate_gbp": 0.0,
    }

    monkeypatch.setattr(prices, "_price_cache", {"ABC.L": 5.0})

    shocked = apply_price_shock(portfolio, "ABC.L", 10)

    assert shocked["accounts"][0]["value_estimate_gbp"] > 0
    assert shocked["total_value_estimate_gbp"] > 0


def test_apply_historical_event_scales_portfolio():
    portfolio = {
        "accounts": [{"value_estimate_gbp": 100.0}],
        "total_value_estimate_gbp": 100.0,
    }

    shocked = apply_historical_event(portfolio, event_id="dummy", horizons=[1, 5])

    assert 1 in shocked and 5 in shocked
    assert shocked[1]["total_value_estimate_gbp"] < portfolio["total_value_estimate_gbp"]
