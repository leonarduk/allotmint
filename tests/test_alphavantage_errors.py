from datetime import date

import pytest

import backend.config as cfg
import backend.timeseries.fetch_alphavantage_timeseries as av
from backend.timeseries.fetch_alphavantage_timeseries import (
    fetch_alphavantage_timeseries_range,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_information_field_propagated(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"Information": "test info"})

    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: True)
    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ValueError) as exc:
        fetch_alphavantage_timeseries_range("PBR", "US", date(2024, 1, 1), date(2024, 1, 10), api_key="demo")

    assert str(exc.value) == "test info"


def test_information_field_propagated_when_disabled(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"Information": "disabled"})

    monkeypatch.setattr(av, "is_valid_ticker", lambda *a, **k: True)
    monkeypatch.setattr(cfg.config, "alpha_vantage_enabled", False)
    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ValueError) as exc:
        fetch_alphavantage_timeseries_range(
            "IBM", "US", date(2024, 1, 1), date(2024, 1, 10), api_key="demo"
        )

    assert str(exc.value) == "disabled"
