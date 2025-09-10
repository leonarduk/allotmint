from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.pension import state_pension_age_uk


def test_pension_route_uses_owner_metadata(monkeypatch):
    captured_owner = []

    def fake_meta(owner: str):
        captured_owner.append(owner)
        return {"dob": "1980-01-01"}

    called = {}

    def fake_forecast(**kwargs):
        called.update(kwargs)
        return {"forecast": []}

    monkeypatch.setattr("backend.routes.pension.load_person_meta", fake_meta)
    monkeypatch.setattr("backend.routes.pension.forecast_pension", fake_forecast)
    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio",
        lambda owner: {
            "accounts": [
                {"account_type": "sipp", "value_estimate_gbp": 100.0},
                {"account_type": "isa", "value_estimate_gbp": 50.0},
                {"account_type": "SIPP", "value_estimate_gbp": 200.0},
            ]
        },
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/pension/forecast", params={"owner": "alice", "death_age": 90})
    assert resp.status_code == 200
    assert captured_owner == ["alice"]
    expected_age = state_pension_age_uk("1980-01-01")
    assert called["retirement_age"] == expected_age
    body = resp.json()
    assert body["retirement_age"] == expected_age
    assert isinstance(body["current_age"], float)
    assert body["pension_pot_gbp"] == 300.0


def test_pension_route_missing_dob(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta", lambda owner: {}
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/pension/forecast", params={"owner": "bob", "death_age": 90})
    assert resp.status_code == 400


def test_pension_route_invalid_dob(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta", lambda owner: {"dob": "bad"}
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/pension/forecast", params={"owner": "bob", "death_age": 90})
    assert resp.status_code == 400
