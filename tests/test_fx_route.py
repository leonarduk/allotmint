"""``GET /fx/gbp-rate`` for base-currency reporting (#9768)."""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes import fx as fx_route
from backend.timeseries.cache import is_cache_only


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def rates(monkeypatch):
    """Serve the GBP rate from a dict; record whether each lookup ran cache-only."""
    table: dict[str, tuple[float | None, str | None]] = {"GBP": (1.0, None)}
    calls: list[tuple[str, bool]] = []

    def fake(currency):
        calls.append((currency, is_cache_only()))
        return table.get(currency, (None, "missing"))

    monkeypatch.setattr(fx_route, "fx_rate_to_gbp_with_source", fake)
    return table, calls


def test_returns_cached_rate_and_source(client, rates):
    table, calls = rates
    table["USD"] = (0.79, "cache")

    resp = client.get("/fx/gbp-rate?currency=usd")

    assert resp.status_code == 200
    assert resp.json() == {"currency": "USD", "gbp_per_unit": 0.79, "source": "cache"}
    # A page request never fetches from Yahoo (#8028).
    assert calls == [("USD", True)]


def test_missing_rate_is_null_not_invented(client, rates):
    resp = client.get("/fx/gbp-rate?currency=XYZ")

    assert resp.json() == {"currency": "XYZ", "gbp_per_unit": None, "source": "missing"}


@pytest.mark.parametrize("currency", ["GBP", "GBX"])
def test_sterling_is_one(client, rates, currency):
    assert client.get(f"/fx/gbp-rate?currency={currency}").json() == {
        "currency": "GBP",
        "gbp_per_unit": 1.0,
        "source": None,
    }


@pytest.mark.parametrize("currency", ["US", "USDX", "U5D", ""])
def test_rejects_invalid_codes(client, rates, currency):
    assert client.get(f"/fx/gbp-rate?currency={currency}").status_code == 400
