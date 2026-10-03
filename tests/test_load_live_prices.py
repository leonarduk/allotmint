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


def test_load_live_prices_adm_gbx_quote_not_double_scaled(monkeypatch):
    """Regression test for #8597: ADM.L (GBX metadata) was listed in
    ``data/scaling_overrides.json`` as 0.1, so a 3588p quote became 358.8 and
    then -- because 0.1 != the pence factor -- was divided by 100 again,
    giving 3.588. Uses the real ``get_scaling_override`` and overrides file.
    """

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "quoteResponse": {
                    "result": [
                        {
                            "symbol": "ADM.L",
                            "regularMarketPrice": 3588.0,
                            "regularMarketTime": 1700000000,
                        }
                    ]
                }
            }

    monkeypatch.setattr(holding_utils.requests, "get", lambda url, timeout: Resp())
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda t: {"currency": "GBX"})

    prices = holding_utils.load_live_prices(["ADM.L"])
    assert prices["ADM.L"]["price"] == pytest.approx(35.88)
