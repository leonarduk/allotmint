import json
from datetime import date
import pandas as pd

from backend.common import portfolio_utils


def test_refresh_snapshot_case_insensitive_close(monkeypatch, tmp_path):
    ticker = "ABC.L"
    today = date.today()
    df = pd.DataFrame({"Date": [pd.Timestamp(today)], "Close": [123.45]})

    monkeypatch.setattr(portfolio_utils, "list_all_unique_tickers", lambda: [ticker])
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries_range", lambda **kwargs: df)
    monkeypatch.setattr(portfolio_utils, "get_scaling_override", lambda *a, **k: 1)
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", tmp_path / "latest_prices.json")
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})

    portfolio_utils.refresh_snapshot_in_memory_from_timeseries(days=1)

    snapshot = portfolio_utils._PRICE_SNAPSHOT
    assert ticker in snapshot
    info = snapshot[ticker]
    assert info["last_price"] == 123.45
    assert info["last_price_date"] == today.strftime("%Y-%m-%d")

    file_data = json.loads((tmp_path / "latest_prices.json").read_text())
    assert ticker in file_data
    assert file_data[ticker]["last_price"] == 123.45


def test_refresh_snapshot_skips_missing_close(monkeypatch, tmp_path):
    ticker = "XYZ.L"
    today = date.today()
    df = pd.DataFrame({"Date": [pd.Timestamp(today)], "High": [1.23]})

    monkeypatch.setattr(portfolio_utils, "list_all_unique_tickers", lambda: [ticker])
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries_range", lambda **kwargs: df)
    monkeypatch.setattr(portfolio_utils, "get_scaling_override", lambda *a, **k: 1)
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", tmp_path / "latest_prices.json")
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})

    portfolio_utils.refresh_snapshot_in_memory_from_timeseries(days=1)

    snapshot = portfolio_utils._PRICE_SNAPSHOT
    assert ticker not in snapshot

    file_data = json.loads((tmp_path / "latest_prices.json").read_text())
    assert ticker not in file_data
