import sys
from types import SimpleNamespace

import backend.common.data_loader as dl
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.pension import state_pension_age_uk
from backend.config import config


def test_pension_route_uses_owner_metadata(monkeypatch):
    captured_owner = []

    def fake_meta(owner: str, root=None):  # pragma: no cover - signature match
        captured_owner.append(owner)
        return {"dob": "1980-01-01"}

    called = {}

    def fake_forecast(**kwargs):
        called.update(kwargs)
        return {"forecast": [], "projected_pot_gbp": 0.0}

    def fake_portfolio(owner: str, root=None):  # pragma: no cover - signature match
        return {
            "accounts": [
                {"account_type": "sipp", "value_estimate_gbp": 100},
                {"account_type": "isa", "value_estimate_gbp": 200},
                {"account_type": "SIPP", "value_estimate_gbp": 50},
            ]
        }

    monkeypatch.setattr("backend.routes.pension.load_person_meta", fake_meta)
    monkeypatch.setattr("backend.routes.pension.forecast_pension", fake_forecast)
    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio", fake_portfolio
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get(
            "/pension/forecast", params={"owner": "alice", "death_age": 90}
        )
    assert resp.status_code == 200
    assert captured_owner == ["alice"]
    expected_age = state_pension_age_uk("1980-01-01")
    assert called["retirement_age"] == expected_age
    body = resp.json()
    assert body["retirement_age"] == expected_age
    assert isinstance(body["current_age"], float)
    assert body["dob"] == "1980-01-01"
    assert body["pension_pot_gbp"] == 150
    assert called["initial_pot"] == 150


def test_pension_route_missing_dob(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta", lambda owner, root=None: {}
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/pension/forecast", params={"owner": "bob", "death_age": 90})
    assert resp.status_code == 400


def test_pension_route_invalid_dob(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta", lambda owner, root=None: {"dob": "bad"}
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/pension/forecast", params={"owner": "bob", "death_age": 90})
    assert resp.status_code == 400


def test_pension_route_prefers_monthly_over_annual(monkeypatch):
    called = {}

    def fake_meta(owner: str, root=None):  # pragma: no cover - signature match
        return {"dob": "1980-01-01"}

    def fake_forecast(**kwargs):
        called.update(kwargs)
        return {"forecast": []}

    monkeypatch.setattr("backend.routes.pension.load_person_meta", fake_meta)
    monkeypatch.setattr("backend.routes.pension.forecast_pension", fake_forecast)
    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio", lambda o, root=None: {"accounts": []}
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get(
            "/pension/forecast",
            params={
                "owner": "alice",
                "death_age": 90,
                "contribution_annual": 1000,
                "contribution_monthly": 100,
            },
        )
    assert resp.status_code == 200
    assert called.get("contribution_annual") == 1200


def test_pension_route_rejects_death_age_not_exceeding_retirement(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.state_pension_age_uk", lambda dob: 67
    )
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta",
        lambda owner, root=None: {"dob": "1980-01-01"},
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get(
            "/pension/forecast", params={"owner": "carol", "death_age": 67}
        )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "death_age must exceed retirement_age"}


def test_pension_route_propagates_missing_portfolio(monkeypatch):
    monkeypatch.setattr(
        "backend.routes.pension.state_pension_age_uk", lambda dob: 67
    )
    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta",
        lambda owner, root=None: {"dob": "1980-01-01"},
    )

    def fake_portfolio(owner: str, root=None):  # pragma: no cover - signature match
        raise FileNotFoundError("no portfolio for owner")

    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio", fake_portfolio
    )
    app = create_app()
    with TestClient(app) as client:
        resp = client.get(
            "/pension/forecast", params={"owner": "dave", "death_age": 90}
        )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "no portfolio for owner"}


def test_pension_route_falls_back_to_local_metadata(tmp_path, monkeypatch):
    owner = "demo"
    owner_dir = tmp_path / owner
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text('{"dob": "1980-01-01"}', encoding="utf-8")

    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "repo_root", tmp_path)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    monkeypatch.setenv(dl.DATA_BUCKET_ENV, "bucket")

    def raising_client(name):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=raising_client))

    def fake_portfolio(owner: str, root=None):  # pragma: no cover - signature match
        return {"accounts": [{"account_type": "sipp", "value_estimate_gbp": 100.0}]}

    captured: dict[str, object] = {}

    def fake_forecast(**kwargs):  # pragma: no cover - signature match
        captured.update(kwargs)
        return {"forecast": []}

    monkeypatch.setattr("backend.routes.pension.build_owner_portfolio", fake_portfolio)
    monkeypatch.setattr("backend.routes.pension.forecast_pension", fake_forecast)

    app = create_app()
    app.state.accounts_root = tmp_path

    with TestClient(app) as client:
        resp = client.get(
            "/pension/forecast", params={"owner": owner, "death_age": 90}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dob"] == "1980-01-01"
    assert captured.get("dob") == "1980-01-01"
