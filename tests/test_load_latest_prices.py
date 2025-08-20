import pandas as pd
import pytest

from backend.common import holding_utils


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"Date": [1], "Close_gbp": [2.0], "Close": [1.0]}, 2.0),
        ({"Date": [1], "Close": [1.5]}, 1.5),
        ({"Date": [1], "close_gbp": [3.0]}, 3.0),
        ({"Date": [1], "close": [4.0]}, 4.0),
    ],
)
def test_load_latest_prices_selects_close_column(monkeypatch, data, expected):
    def fake_load_meta_timeseries_range(ticker, exchange, start_date, end_date):
        return pd.DataFrame(data)

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load_meta_timeseries_range)

    prices = holding_utils.load_latest_prices(["ABC.L"])
    assert prices["ABC.L"] == expected


def test_load_latest_prices_applies_scaling(monkeypatch):
    df = pd.DataFrame({"Date": [1], "Close": [20.0]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 0.5)

    prices = holding_utils.load_latest_prices(["ABC.L"])
    assert prices["ABC.L"] == 10.0
