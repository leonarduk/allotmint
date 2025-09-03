import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.virtual_portfolio import (
    VirtualPortfolio,
    VirtualPortfolioSummary,
)
from backend.config import config


@pytest.fixture()
def vp_client():
    config.skip_snapshot_warm = True
    config.offline_mode = True
    app = create_app()
    with TestClient(app) as c:
        token = c.post("/token", json={"id_token": "good"}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def test_list_virtual_portfolios(monkeypatch, vp_client):
    fake_list = [
        VirtualPortfolioSummary(id="vp1", name="First"),
        VirtualPortfolioSummary(id="vp2", name="Second"),
    ]
    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.list_virtual_portfolio_metadata",
        lambda: fake_list,
    )

    resp = vp_client.get("/virtual-portfolios")
    assert resp.status_code == 200
    assert resp.json() == [item.model_dump() for item in fake_list]


def test_get_virtual_portfolio(monkeypatch, vp_client):
    vp_data = {"id": "vp1", "name": "First", "holdings": []}
    vp = VirtualPortfolio(**vp_data)
    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.load_virtual_portfolio",
        lambda _id: vp,
    )

    resp = vp_client.get("/virtual-portfolios/vp1")
    assert resp.status_code == 200
    assert resp.json() == vp_data


def test_create_or_update_virtual_portfolio(monkeypatch, vp_client):
    vp_data = {"id": "vp1", "name": "First", "holdings": []}
    vp = VirtualPortfolio(**vp_data)

    def fake_save(vp_in):
        assert vp_in == vp
        return vp

    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.save_virtual_portfolio",
        fake_save,
    )

    resp = vp_client.post("/virtual-portfolios", json=vp_data)
    assert resp.status_code == 200
    assert resp.json() == vp_data


def test_delete_virtual_portfolio(monkeypatch, vp_client):
    called = {}

    def fake_delete(vp_id):
        called["vp_id"] = vp_id

    monkeypatch.setattr(
        "backend.routes.virtual_portfolio.delete_virtual_portfolio",
        fake_delete,
    )

    resp = vp_client.delete("/virtual-portfolios/vp1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert called["vp_id"] == "vp1"
