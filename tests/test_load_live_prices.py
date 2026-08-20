import datetime as dt

import pytest

from backend.common import holding_utils


def test_load_live_prices_applies_scaling_and_fx(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

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

    monkeypatch.setattr(holding_utils, "_fx_to_base", lambda c, b, cache: 1.5)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: {"currency": "USD"})

    prices = holding_utils.load_live_prices(["ABC.L"])
    assert prices["ABC.L"]["price"] == pytest.approx(7.5)
    ts = prices["ABC.L"]["timestamp"]
    assert isinstance(ts, dt.datetime) and ts.tzinfo is not None


def test_load_live_prices_scales_pence_quoted_lse_ticker_with_gbp_currency(monkeypatch):
    """Regression test for #6845: a real LSE ticker (GSK.L) whose quote source
    returns raw pence but whose instrument metadata's `currency` is "GBP" (not
    a pence code) used to be treated as an already-correct GBP price -- a
    GBP18.88 stock rendered as GBP1888.00. Uses the real
    ``get_scaling_override`` (unmocked) so this exercises the actual
    ``data/scaling_overrides.json`` fix, not just the mechanism in isolation.
    """

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": "GSK.L",
                            "regularMarketPrice": 1888.0,
                            "regularMarketTime": 1700000000,
                        }
                    ]
                }
            }

    monkeypatch.setattr(holding_utils.requests, "get", lambda url, timeout: Resp())
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: {"currency": "GBP"})

    prices = holding_utils.load_live_prices(["GSK.L"])
    assert prices["GSK.L"]["price"] == pytest.approx(18.88)
