from datetime import date
import pytest

from backend import config as cfg
from backend.timeseries.fetch_alphavantage_timeseries import fetch_alphavantage_timeseries_range
from backend.tasks.quotes import fetch_quote
import requests


def test_alphavantage_timeseries_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "alpha_vantage_enabled", False)

    def fail_get(*args, **kwargs):
        raise AssertionError("network call should not be made")

    monkeypatch.setattr(requests, "get", fail_get)
    df = fetch_alphavantage_timeseries_range("IBM", "US", date(2024, 1, 1), date(2024, 1, 2))
    assert df.empty


def test_fetch_quote_raises_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "alpha_vantage_enabled", False)
    with pytest.raises(RuntimeError):
        fetch_quote("IBM")
