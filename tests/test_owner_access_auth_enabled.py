"""Per-owner checks on protected owner routes with auth enabled (#11351).

The portfolio, VaR, account, performance, reports and alerts routers sit behind
the router-level ``get_current_user`` dependency, which only proves the
caller is signed in. Each route that takes an owner must also call
``ensure_owner_access`` so a signed-in user cannot read (or write) an owner
they are neither, nor the ``email`` of, nor a listed viewer of.

Everything here runs the real ``ensure_owner_access`` against real
``person.json`` files and a real ``POST /token`` login (``user@example.com``
via the conftest Google stub). Only the expensive data builders are stubbed,
so a 200 returns ``_SECRET`` and writes are recorded.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common import look_through, portfolio_utils
from backend.config import config
from backend.routes import alerts as alerts_routes
from backend.routes import portfolio as portfolio_routes
from backend.routes import reports as reports_routes

_SECRET = "owner-data"
_ME = "user@example.com"
# alice: the signed-in user's own owner (by email); carol: lists them as a
# viewer; bob: no relation, so every bob request must be denied.
_PEOPLE = {
    "alice": {"owner": "alice", "email": _ME},
    "bob": {"owner": "bob", "email": "bob@example.com"},
    "carol": {"owner": "carol", "email": "carol@example.com", "viewers": [_ME]},
}
_DEMO_OWNER = "alice"


@pytest.fixture
def writes(monkeypatch):
    """Stub the data builders behind every fixed route; record each write."""
    recorded: list = []
    portfolio = {"owner": "x", "secret": _SECRET, "accounts": []}
    monkeypatch.setattr(portfolio_routes.portfolio_mod, "build_owner_portfolio", lambda owner, *a, **k: portfolio)
    monkeypatch.setattr(portfolio_utils, "aggregate_by_sector", lambda pf: [{"secret": _SECRET}])
    monkeypatch.setattr(portfolio_utils, "aggregate_by_currency", lambda pf: [{"secret": _SECRET}])
    monkeypatch.setattr(look_through, "compute_look_through", lambda pf: {"secret": _SECRET})
    monkeypatch.setattr(
        portfolio_routes,
        "risk",
        SimpleNamespace(
            compute_portfolio_var=lambda owner, **k: {"secret": _SECRET},
            compute_portfolio_var_scenarios=lambda owner, **k: {"scenarios": [], "var_date": None},
            compute_portfolio_var_breakdown=lambda owner, **k: [],
        ),
    )
    pair = lambda *a, **k: (_SECRET, {})  # noqa: E731 - tiny stub
    for name in ("compute_alpha_vs_benchmark", "compute_tracking_error", "compute_max_drawdown"):
        monkeypatch.setattr(portfolio_utils, name, pair)
    for name in (
        "compute_time_weighted_return",
        "compute_xirr",
        "compute_fx_attribution",
        "compute_cagr",
        "compute_cash_apy",
    ):
        monkeypatch.setattr(portfolio_utils, name, lambda *a, **k: _SECRET)
    monkeypatch.setattr(
        portfolio_utils, "compute_total_return", lambda *a, **k: {"total_return_gbp": _SECRET, "total_return_pct": 1}
    )
    monkeypatch.setattr(portfolio_utils, "portfolio_value_breakdown", lambda *a, **k: [{"secret": _SECRET}])
    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", lambda owner, **k: {"secret": _SECRET})
    document = SimpleNamespace(to_dict=lambda: {"secret": _SECRET})
    monkeypatch.setattr(reports_routes, "build_report_document", lambda *a, **k: document)
    monkeypatch.setattr(reports_routes, "report_to_csv", lambda doc: _SECRET)
    monkeypatch.setattr(alerts_routes.alert_utils, "get_user_threshold", lambda user: _SECRET)
    monkeypatch.setattr(alerts_routes.alert_utils, "set_user_threshold", lambda user, t: recorded.append(user))
    monkeypatch.setattr(
        alerts_routes.alert_utils, "set_user_push_subscription", lambda user, sub: recorded.append(user)
    )
    monkeypatch.setattr(alerts_routes.alert_utils, "remove_user_push_subscription", lambda user: recorded.append(user))
    return recorded


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    for owner, person in _PEOPLE.items():
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps(person))
        (tmp_path / owner / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": [], "note": _SECRET})
        )
    return tmp_path


def _signed_in_client(monkeypatch) -> TestClient:
    """Auth enabled, signed in through the real ``/token`` endpoint as ``user@example.com``."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


_PUSH = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}

_READS = {
    "portfolio": lambda o: ("GET", f"/portfolio/{o}", {}),
    "portfolio_sectors": lambda o: ("GET", f"/portfolio/{o}/sectors", {}),
    "portfolio_currencies": lambda o: ("GET", f"/portfolio/{o}/currencies", {}),
    "portfolio_look_through": lambda o: ("GET", f"/portfolio/{o}/look-through", {}),
    "var": lambda o: ("GET", f"/var/{o}", {}),
    "var_breakdown": lambda o: ("GET", f"/var/{o}/breakdown", {}),
    "var_recompute": lambda o: ("POST", f"/var/{o}/recompute", {}),
    "account": lambda o: ("GET", f"/account/{o}/isa", {}),
    "performance": lambda o: ("GET", f"/performance/{o}", {}),
    "performance_alpha": lambda o: ("GET", f"/performance/{o}/alpha", {}),
    "performance_tracking_error": lambda o: ("GET", f"/performance/{o}/tracking-error", {}),
    "performance_max_drawdown": lambda o: ("GET", f"/performance/{o}/max-drawdown", {}),
    "performance_twr": lambda o: ("GET", f"/performance/{o}/twr", {}),
    "performance_total_return": lambda o: ("GET", f"/performance/{o}/total-return", {}),
    "performance_xirr": lambda o: ("GET", f"/performance/{o}/xirr", {}),
    "performance_fx_attribution": lambda o: ("GET", f"/performance/{o}/fx-attribution", {}),
    "performance_holdings": lambda o: ("GET", f"/performance/{o}/holdings", {"params": {"date": "2024-01-02"}}),
    "returns_compare": lambda o: ("GET", "/returns/compare", {"params": {"owner": o}}),
    "report": lambda o: ("GET", f"/reports/{o}", {}),
    "report_csv": lambda o: ("GET", f"/reports/{o}", {"params": {"format": "csv"}}),
    "report_template": lambda o: ("GET", f"/reports/{o}/periodic-summary", {}),
    "alert_settings_get": lambda o: ("GET", f"/alerts/settings/{o}", {}),
}
_WRITES = {
    "alert_settings_set": lambda o: ("POST", f"/alerts/settings/{o}", {"json": {"threshold": 5}}),
    "push_subscription_add": lambda o: ("POST", f"/alerts/push-subscription/{o}", {"json": _PUSH}),
    "push_subscription_delete": lambda o: ("DELETE", f"/alerts/push-subscription/{o}", {}),
}
_ROUTES = {**_READS, **_WRITES}


def _request(client, name, owner):
    method, path, kwargs = _ROUTES[name](owner)
    return client.request(method, path, **kwargs)


@pytest.mark.parametrize("name", sorted(_ROUTES))
def test_signed_in_non_viewer_gets_403_and_no_data(accounts, writes, monkeypatch, name):
    client = _signed_in_client(monkeypatch)

    resp = _request(client, name, "bob")

    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": "Not authorized for this owner"}
    assert _SECRET not in resp.text
    assert writes == []


@pytest.mark.parametrize("name", sorted(_ROUTES))
@pytest.mark.parametrize("owner", ["alice", "carol"])
def test_owner_and_viewer_still_get_200(accounts, writes, monkeypatch, name, owner):
    client = _signed_in_client(monkeypatch)

    resp = _request(client, name, owner)

    assert resp.status_code == 200, resp.text
    if name in _READS:
        assert _SECRET in resp.text


def test_check_matches_a_differently_cased_owner_slug(accounts, writes, monkeypatch):
    client = _signed_in_client(monkeypatch)

    assert client.get("/performance/CAROL").status_code == 200
    assert client.get("/account/CAROL/isa").status_code == 200
    assert client.get("/performance/BOB").status_code == 403
    assert client.get("/account/BOB/isa").status_code == 403


def test_anonymous_request_is_still_401_with_auth_enabled(accounts, writes, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert client.get("/portfolio/alice").status_code == 401
    assert client.get("/performance/alice").status_code == 401


@pytest.mark.parametrize("name", sorted(_ROUTES))
def test_auth_disabled_anonymous_reads_any_owner_unchanged(accounts, writes, monkeypatch, name):
    """``disable_auth`` with ``ENFORCE_OWNER_ACCESS`` off: the check no-ops, as before."""
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)
    client = TestClient(create_app())

    assert _request(client, name, "bob").status_code == 200


def test_auth_disabled_ignores_an_unreadable_token_as_before(accounts, writes, monkeypatch):
    """With ``disable_auth`` on, these routes never resolved the bearer token, and they still don't.

    ``get_active_user`` would 401 an unreadable token (or 403 an unlisted
    Cognito email) in this mode, so the routes use ``get_owner_check_identity``,
    which defers to ``ensure_owner_access`` instead.
    """
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    client = TestClient(create_app())
    client.headers.update({"Authorization": "Bearer not-a-jwt"})

    for name in sorted(_ROUTES):
        assert _request(client, name, "bob").status_code == 200, name


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_is_confined_to_the_demo_owner(accounts, writes, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", _DEMO_OWNER, raising=False)
    token = auth.create_demo_access_token(_DEMO_OWNER)
    client.headers.update({"Authorization": f"Bearer {token}"})

    # Demo tokens are read-only (#7407): only the GET routes apply here.
    for name in sorted(n for n in _READS if _READS[n]("x")[0] == "GET"):
        assert _request(client, name, _DEMO_OWNER).status_code == 200, name
        denied = _request(client, name, "bob")
        assert denied.status_code == 403, name
        assert _SECRET not in denied.text, name


def test_enforce_owner_access_flag_still_applies(accounts, writes, monkeypatch):
    """#11350's flag: ``disable_auth`` plus ``ENFORCE_OWNER_ACCESS`` checks the gateway identity."""
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", _ME, raising=False)

    assert client.get("/portfolio/alice").status_code == 200
    assert client.get("/performance/carol").status_code == 200
    assert client.get("/portfolio/bob").status_code == 403
    assert client.get("/reports/bob").status_code == 403


def test_end_to_end_owner_isolation_with_auth_enabled(accounts, writes, monkeypatch):
    """One signed-in session across the fixed routes: own data yes, another owner's no."""
    client = _signed_in_client(monkeypatch)

    assert client.get("/portfolio/alice").json()["secret"] == _SECRET
    assert client.get("/account/alice/isa").json()["note"] == _SECRET
    bob_account = client.get("/account/bob/isa")
    assert bob_account.status_code == 403
    assert _SECRET not in bob_account.text
    assert client.get("/reports/bob", params={"format": "csv"}).status_code == 403
    assert client.post("/alerts/push-subscription/bob", json=_PUSH).status_code == 403
    assert writes == []
