import datetime as dt

import pandas as pd

from backend.common import instrument_api as ia


def test_timeseries_uses_portfolio_exchange(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2023, 1, 9)

    monkeypatch.setattr(ia.dt, "date", FixedDate)
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})
    monkeypatch.setattr(ia, "_TICKER_EXCHANGE_MAP", {"XYZ": "N"})

    captured = {}

    def fake_has_cached(sym, ex):
        captured["cache_ex"] = ex
        return True

    def fake_load(sym, ex, start_date, end_date):
        captured["load_ex"] = ex
        return pd.DataFrame({"date": [end_date], "close": [1.0]})

    monkeypatch.setattr(ia, "has_cached_meta_timeseries", fake_has_cached)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", fake_load)

    res = ia.timeseries_for_ticker("XYZ", days=1)
    assert captured["cache_ex"] == "N"
    assert captured["load_ex"] == "N"
    assert res["prices"] == [{"date": "2023-01-08", "close": 1.0, "close_gbp": 1.0}]
    assert set(res["mini"].keys()) == {"7", "30", "180"}
