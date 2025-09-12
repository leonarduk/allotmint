import datetime as dt
import pytest

from backend.common import holding_utils


def test_load_live_prices_applies_scaling_and_fx(monkeypatch):
    class Resp:
        def json(self):
            return {
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": "ABC.L",
                            "regularMarketPrice": 10.0,
                            "regularMarketTime": 1700000000,
                        }
                    ]
                }
            }

    monkeypatch.setattr(holding_utils.requests, "get", lambda url, timeout: Resp())
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 0.5)

    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(pu, "_fx_to_gbp", lambda c, cache: 1.5)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: {"currency": "USD"})

    prices = holding_utils.load_live_prices(["ABC.L"])
    assert prices["ABC.L"]["price"] == pytest.approx(7.5)
    ts = prices["ABC.L"]["timestamp"]
    assert isinstance(ts, dt.datetime) and ts.tzinfo is not None
