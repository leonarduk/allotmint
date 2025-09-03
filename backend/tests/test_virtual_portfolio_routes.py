from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.virtual_portfolio import router
from backend.common.virtual_portfolio import (
    VirtualPortfolio,
    VirtualPortfolioSummary,
)


def create_app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_list_virtual_portfolios(monkeypatch):
    app = create_app()
    sample = [VirtualPortfolioSummary(id="vp1", name="My VP")]
    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.list_virtual_portfolio_metadata",
        lambda: sample,
    )
    with TestClient(app) as client:
        resp = client.get("/virtual-portfolios")
    assert resp.status_code == 200
    assert resp.json() == [s.model_dump() for s in sample]


def test_get_virtual_portfolio(monkeypatch):
    app = create_app()
    portfolio = VirtualPortfolio(id="vp1", name="My VP", holdings=[])
    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.load_virtual_portfolio",
        lambda vp_id: portfolio if vp_id == "vp1" else None,
    )
    with TestClient(app) as client:
        ok_resp = client.get("/virtual-portfolios/vp1")
        missing_resp = client.get("/virtual-portfolios/missing")
    assert ok_resp.status_code == 200
    assert ok_resp.json() == portfolio.model_dump()
    assert missing_resp.status_code == 404


def test_create_update_virtual_portfolio(monkeypatch):
    app = create_app()
    saved = {}

    def fake_save(vp: VirtualPortfolio) -> VirtualPortfolio:
        saved["vp"] = vp
        return vp

    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.save_virtual_portfolio",
        fake_save,
    )
    payload = {"id": "vp1", "name": "My VP", "holdings": []}
    with TestClient(app) as client:
        resp = client.post("/virtual-portfolios", json=payload)
    assert resp.status_code == 200
    assert resp.json() == payload
    assert saved["vp"] == VirtualPortfolio(**payload)


def test_delete_virtual_portfolio(monkeypatch):
    app = create_app()
    deleted = {}

    def fake_delete(vp_id: str) -> None:
        deleted["id"] = vp_id

    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.delete_virtual_portfolio",
        fake_delete,
    )
    with TestClient(app) as client:
        resp = client.delete("/virtual-portfolios/vp1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert deleted["id"] == "vp1"
