"""Owner authorization on unprotected read routes (#11346, follow-up to #11342).

The tax, compliance, pension and metrics routers are registered without auth
dependencies, so each route that takes an owner must call
``ensure_owner_access`` itself before reading (or caching) that owner's data.
Synthetic owners only; the pro-only cores are stubbed.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.routes import compliance as compliance_routes
from backend.routes import metrics as metrics_routes
from backend.routes import pension as pension_routes
from backend.routes import tax as tax_routes

_SECRET = {"secret": "owner-data"}


@pytest.fixture
def stub_cores(tmp_path, monkeypatch):
    """Stub every data source so a 200 returns ``_SECRET`` and writes are recorded."""
    writes = []
    monkeypatch.setattr(tax_routes, "current_tax_year", lambda: 2024)
    monkeypatch.setattr(tax_routes, "remaining_allowances", lambda owner, ty: _SECRET)
    monkeypatch.setattr(
        compliance_routes,
        "compliance",
        SimpleNamespace(
            check_owner=lambda owner, root, scaffold_missing=False: {"owner": owner, **_SECRET},
            check_trade=lambda trade, root, scaffold_missing=False: {"owner": trade["owner"], **_SECRET},
        ),
    )
    monkeypatch.setattr(compliance_routes, "ensure_owner_scaffold", lambda owner, root: writes.append(owner))
    monkeypatch.setattr(metrics_routes, "load_metrics", lambda owner: None)
    monkeypatch.setattr(metrics_routes, "compute_and_store_metrics", lambda owner: writes.append(owner) or _SECRET)
    monkeypatch.setattr(
        pension_routes,
        "load_person_metadata",
        lambda owner, root=None: SimpleNamespace(dob="1980-01-01"),
    )
    monkeypatch.setattr(pension_routes, "build_owner_portfolio", lambda owner, **kw: {"accounts": []})
    return writes


@pytest.fixture
def client(tmp_path, monkeypatch, stub_cores):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    for owner in ("alice", "bob"):
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps({"owner": owner}))
    return TestClient(create_app())


@pytest.fixture
def checked(monkeypatch):
    """Record each owner checked on every fixed router; allow only ``alice``."""
    seen = []

    def allow_only_alice(identity, owner, accounts_root=None):
        seen.append(owner)
        if owner != "alice":
            raise PermissionDeniedError("nope")

    for module in (tax_routes, compliance_routes, pension_routes, metrics_routes):
        monkeypatch.setattr(module, "ensure_owner_access", allow_only_alice, raising=False)
    return seen


def _request(client, route, owner):
    method, path, kwargs = route(owner)
    return client.request(method, path, **kwargs)


_ROUTES = {
    "tax_allowances": lambda o: ("GET", "/tax/allowances", {"params": {"owner": o}}),
    "compliance_owner": lambda o: ("GET", f"/compliance/{o}", {}),
    "compliance_validate": lambda o: (
        "POST",
        "/compliance/validate",
        {"json": {"owner": o, "ticker": "AAA.L", "type": "BUY", "date": "2024-01-02"}},
    ),
    "pension_profile": lambda o: ("GET", "/pension/profile", {"params": {"owner": o}}),
    "pension_forecast": lambda o: ("GET", "/pension/forecast", {"params": {"owner": o, "death_age": 95}}),
    "metrics": lambda o: ("GET", f"/metrics/{o}", {}),
}


@pytest.mark.parametrize("name", sorted(_ROUTES))
def test_denied_owner_gets_403_without_data(client, checked, name):
    resp = _request(client, _ROUTES[name], "bob")

    assert resp.status_code == 403
    assert checked == ["bob"]
    assert "owner-data" not in resp.text
    assert "1980-01-01" not in resp.text


@pytest.mark.parametrize("name", sorted(_ROUTES))
def test_allowed_owner_still_gets_data(client, checked, name):
    resp = _request(client, _ROUTES[name], "alice")

    assert resp.status_code == 200
    assert checked == ["alice"]


def test_denied_metrics_does_not_compute_or_cache(client, checked, stub_cores):
    assert _request(client, _ROUTES["metrics"], "bob").status_code == 403
    assert stub_cores == []


def test_denied_compliance_validate_does_not_scaffold(client, checked, stub_cores, tmp_path):
    resp = client.post("/compliance/validate", json={"owner": "carol", "ticker": "AAA.L"})

    assert resp.status_code == 403
    assert checked == ["carol"]
    assert stub_cores == []
    assert not (tmp_path / "carol").exists()


def test_compliance_checks_the_canonical_owner_directory(client, checked):
    assert client.get("/compliance/ALICE").status_code == 200
    assert checked == ["alice"]


def test_auth_disabled_reads_any_owner_unchanged(client, monkeypatch):
    """With auth off the real check no-ops, so every route still answers."""
    monkeypatch.setattr(config, "disable_auth", True)
    for name in sorted(_ROUTES):
        assert _request(client, _ROUTES[name], "bob").status_code == 200, name


# ---- end to end with auth enabled ------------------------------------------


def test_auth_enabled_signed_in_user_cannot_read_another_owner(tmp_path, monkeypatch, stub_cores):
    """The real ``ensure_owner_access`` and person metadata: ``user@example.com`` owns ``alice`` only."""
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    emails = {"alice": "user@example.com", "bob": "bob@example.com"}
    for owner in ("alice", "bob"):
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps({"owner": owner, "email": emails[owner]}))
        (tmp_path / owner / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": []})
        )
    client = TestClient(create_app())

    anonymous = client.get("/pension/profile", params={"owner": "alice"})
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    for name in sorted(_ROUTES):
        denied = _request(client, _ROUTES[name], "bob")
        allowed = _request(client, _ROUTES[name], "alice")
        assert denied.status_code == 403, name
        assert "owner-data" not in denied.text, name
        assert allowed.status_code == 200, name
    assert anonymous.status_code == 401
