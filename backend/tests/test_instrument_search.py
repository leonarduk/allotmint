from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import instrument

SAMPLE_INSTRUMENTS = [
    {"ticker": "ABC.L", "name": "ABC Company", "sector": "Tech", "region": "UK"},
    {"ticker": "XYZ.N", "name": "XYZ Corp", "sector": "Finance", "region": "US"},
    {"ticker": "ALPHA.L", "name": "Alpha Inc", "sector": "Tech", "region": "UK"},
]


def create_app(monkeypatch):
    app = FastAPI()
    app.include_router(instrument.router)
    monkeypatch.setattr("backend.common.instruments.list_instruments", lambda: SAMPLE_INSTRUMENTS)
    return app


def test_search_returns_matching_instruments(monkeypatch):
    app = create_app(monkeypatch)
    with TestClient(app) as client:
        resp = client.get("/instrument/search", params={"q": "alpha"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "ALPHA.L", "name": "Alpha Inc", "sector": "Tech", "region": "UK"}]


def test_sector_region_filters(monkeypatch):
    app = create_app(monkeypatch)
    with TestClient(app) as client:
        resp = client.get("/instrument/search", params={"q": "c"})
        resp_sector = client.get("/instrument/search", params={"q": "c", "sector": "Finance"})
        resp_region = client.get("/instrument/search", params={"q": "c", "region": "US"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp_sector.json() == [{"ticker": "XYZ.N", "name": "XYZ Corp", "sector": "Finance", "region": "US"}]
    assert resp_region.json() == [{"ticker": "XYZ.N", "name": "XYZ Corp", "sector": "Finance", "region": "US"}]


def test_invalid_input(monkeypatch):
    app = create_app(monkeypatch)
    with TestClient(app) as client:
        resp = client.get("/instrument/search")
    assert resp.status_code == 400
