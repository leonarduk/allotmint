"""Regression coverage for the require_core-before-validation ordering that
frontend/src/api.ts's checkScreenerAvailable() probe depends on (#7221).

Deliberately does not use ``pytest.importorskip("allotmint_pro")`` (unlike
``tests/routes/test_screener.py``, which importorskips when the private
package isn't installed) -- the whole point of this test is to exercise the
*gated* (package not installed) path, so it must stay green in public/
free-tier CI where the private package is absent.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import core_feature_unavailable_handler
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.routes import screener


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(screener.router)
    # Mirrors backend.app.create_app()'s wiring for this one error type,
    # without paying for the rest of create_app()'s setup (config, auth,
    # lifespan, ...) that this route-level test doesn't need.
    app.add_exception_handler(CoreFeatureUnavailableError, core_feature_unavailable_handler)
    return TestClient(app)


def test_screener_returns_402_when_pro_package_not_installed(monkeypatch):
    """GET /screener/?tickers= must 402, not 400/422, when ``screen`` is unavailable.

    frontend/src/api.ts's checkScreenerAvailable() probes with an empty
    ticker list specifically because backend/routes/screener.py's
    require_core() check runs *before* the "no tickers supplied"
    validation. If that ordering were ever reversed -- e.g. by a
    "validate input first" refactor -- a gated deployment would answer the
    probe with 400 instead of 402, the frontend would conclude the
    screener is available, and the up-front gate (#7221) would silently
    stop working while CI stayed green.
    """
    client = _client()
    monkeypatch.setattr(screener, "screen", None)

    resp = client.get("/screener", params={"tickers": ""})

    assert resp.status_code == 402
    assert "Screener" in resp.json()["detail"]


def test_screener_402_takes_priority_over_valid_tickers(monkeypatch):
    """The gate fires for an otherwise-valid request too, not only empty probes."""
    client = _client()
    monkeypatch.setattr(screener, "screen", None)

    resp = client.get("/screener", params={"tickers": "AZN.L"})

    assert resp.status_code == 402
