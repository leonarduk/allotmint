import backend.common.prices as prices
from backend.utils.scenario_tester import apply_price_shock


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
