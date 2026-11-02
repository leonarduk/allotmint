"""Owner scoping on routes that read across every owner (#11355).

``/custom-query/run``, ``/scenario*`` and ``/instrument/``'s ``positions``
cover every owner instead of one named owner, so the per-owner checks of
#11351 don't apply to them. Each one must list exactly the owners the caller
may see (the ``list_plots(current_user=...)`` rule behind ``/owners``). Owners
the caller names explicitly but may not see get a 403, as on a per-owner
route. With ``disable_auth`` and ``ENFORCE_OWNER_ACCESS`` off, nothing changes.

Runs against real ``person.json`` files and real ``POST /token`` logins
(``user@example.com`` via the conftest Google stub). Only the portfolio
builders and price lookups are stubbed. ``build_owner_portfolio`` lists plots
without a user and finds none with auth enabled, so it can't be used here.
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common.portfolio_loader import list_portfolios
from backend.config import config
from backend.routes import instrument as instrument_routes
from backend.routes import scenario as scenario_routes

_ME = "user@example.com"
_SHARED = "SHR.L"
# alice: the signed-in user's own owner (by email); carol: lists them as a
# viewer; bob: no relation, so bob's data must never reach them.
_PEOPLE = {
    "alice": {"owner": "alice", "email": _ME},
    "bob": {"owner": "bob", "email": "bob@example.com"},
    "carol": {"owner": "carol", "email": "carol@example.com", "viewers": [_ME]},
}
_OWN_TICKER = {"alice": "ALC.L", "bob": "BOB.L", "carol": "CAR.L"}
_MINE = {"alice", "carol"}
_EVERYONE = {"alice", "bob", "carol"}
_FORBIDDEN = {"detail": "Not authorized for this owner"}


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    """Three owners on disk, each holding their own ticker plus ``_SHARED``."""
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    for owner, person in _PEOPLE.items():
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps(person))
        holdings = [{"ticker": _OWN_TICKER[owner], "units": 1}, {"ticker": _SHARED, "units": 2}]
        (tmp_path / owner / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": holdings})
        )
    return tmp_path


@pytest.fixture
def builders(monkeypatch):
    """Stub the per-owner portfolio builds and the price lookups."""

    def portfolio(owner, *a, **k):
        holding = {"ticker": _SHARED, "units": 2, "market_value_gbp": 2.0}
        return {
            "owner": owner,
            "total_value_estimate_gbp": 2.0,
            "accounts": [{"account_type": "isa", "holdings": [holding]}],
        }

    monkeypatch.setattr(scenario_routes, "build_owner_portfolio", portfolio)
    monkeypatch.setattr(scenario_routes, "apply_historical_event", lambda pf, **k: {"1d": {"total_value_gbp": 1.0}})
    monkeypatch.setattr(scenario_routes, "holding_fallback", lambda *a, **k: None)
    monkeypatch.setattr(instrument_routes, "build_owner_portfolio", portfolio)
    monkeypatch.setattr(instrument_routes, "load_meta_timeseries_range", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(instrument_routes, "get_security_meta", lambda t: {"name": "Shared plc"})


_TODAY = dt.date.today().isoformat()
_QUERY = {"start": "2024-01-02", "end": _TODAY, "metrics": []}


def _owners_from_rows(resp):
    return {row["owner"] for row in resp.json()["results"]}


def _owners_from_list(resp):
    return {row["owner"] for row in resp.json()}


def _owners_from_positions(resp):
    return {row["owner"] for row in resp.json()["positions"]}


def _query_tickers_owners(resp):
    """Owners whose own ticker shows up in a ticker-only result."""
    tickers = {row["ticker"] for row in resp.json()["results"]}
    return {owner for owner, ticker in _OWN_TICKER.items() if ticker in tickers}


# name -> (method, path, request kwargs, how to read the owners off a 200)
_ALL_OWNER_ROUTES = {
    "query_post": ("POST", "/custom-query/run", {"json": _QUERY}, _query_tickers_owners),
    "query_get": (
        "GET",
        "/custom-query/run",
        {"params": {"start": "2024-01-02", "end": _TODAY}},
        _query_tickers_owners,
    ),
    "scenario": ("GET", "/scenario", {"params": {"ticker": _SHARED, "pct": 5}}, _owners_from_list),
    "scenario_fx": ("GET", "/scenario/fx", {"params": {"currency": "USD", "pct": -10}}, _owners_from_list),
    "scenario_historical": (
        "GET",
        "/scenario/historical",
        {"params": {"date": "2024-01-02", "horizons": "1d"}},
        _owners_from_list,
    ),
    "instrument_positions": (
        "GET",
        "/instrument/",
        {"params": {"ticker": _SHARED, "format": "json"}},
        _owners_from_positions,
    ),
}
_GET_ROUTES = sorted(n for n, r in _ALL_OWNER_ROUTES.items() if r[0] == "GET")


def _owners_seen(client, name):
    method, path, kwargs, read = _ALL_OWNER_ROUTES[name]
    resp = client.request(method, path, **kwargs)
    assert resp.status_code == 200, (name, resp.status_code, resp.text)
    return read(resp)


def _named_query(client, owners, method="POST"):
    if method == "POST":
        return client.post("/custom-query/run", json={**_QUERY, "owners": owners})
    params = {"start": "2024-01-02", "end": _TODAY, "owners": ",".join(owners)}
    return client.get("/custom-query/run", params=params)


def _signed_in_client(monkeypatch) -> TestClient:
    """Auth enabled, signed in through the real ``/token`` endpoint as ``user@example.com``."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _enforced_client(monkeypatch, login=_ME) -> TestClient:
    """``disable_auth`` with ``ENFORCE_OWNER_ACCESS`` on; identity from ``local_login_email``."""
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", login, raising=False)
    return client


# ---------------------------------------------------------------- auth enabled


@pytest.mark.parametrize("name", sorted(_ALL_OWNER_ROUTES))
def test_auth_enabled_all_owners_path_lists_only_visible_owners(accounts, builders, monkeypatch, name):
    client = _signed_in_client(monkeypatch)

    assert _owners_seen(client, name) == _MINE


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_auth_enabled_naming_an_unrelated_owner_is_403(accounts, builders, monkeypatch, method):
    client = _signed_in_client(monkeypatch)

    for owners in (["bob"], ["alice", "bob"], ["BOB"]):
        resp = _named_query(client, owners, method)
        assert resp.status_code == 403, (owners, resp.text)
        assert resp.json() == _FORBIDDEN
        assert _OWN_TICKER["bob"] not in resp.text


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize("owner", ["alice", "carol"])
def test_auth_enabled_owner_and_viewer_still_get_their_own_rows(accounts, builders, monkeypatch, method, owner):
    client = _signed_in_client(monkeypatch)

    resp = _named_query(client, [owner], method)

    assert resp.status_code == 200, resp.text
    assert _query_tickers_owners(resp) == {owner}


def test_auth_enabled_holding_metric_rows_carry_only_visible_owners(accounts, builders, monkeypatch):
    monkeypatch.setattr("backend.routes.query._gbp_price", lambda *a, **k: 1.0)
    client = _signed_in_client(monkeypatch)

    resp = client.post("/custom-query/run", json={**_QUERY, "metrics": ["market_value_gbp"]})

    assert resp.status_code == 200, resp.text
    assert _owners_from_rows(resp) == _MINE


def test_auth_enabled_anonymous_scenario_is_401(accounts, builders, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert client.get("/scenario", params={"ticker": _SHARED, "pct": 5}).status_code == 401
    assert client.post("/custom-query/run", json=_QUERY).status_code == 401


def test_auth_enabled_anonymous_instrument_keeps_prices_but_no_positions(accounts, builders, monkeypatch):
    """``/instrument/`` serves public price history; an anonymous caller just gets no holdings."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    resp = client.get("/instrument/", params={"ticker": _SHARED, "format": "json"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["positions"] == []


# ----------------------------------------------------------------- demo tokens


@pytest.mark.parametrize("disable_auth", [True, False])
@pytest.mark.parametrize("name", _GET_ROUTES)
def test_demo_token_sees_only_the_demo_owner(accounts, builders, monkeypatch, disable_auth, name):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "alice", raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token('alice')}"})

    assert _owners_seen(client, name) == {"alice"}


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_naming_another_owner_is_403(accounts, builders, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "alice", raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token('alice')}"})

    assert _named_query(client, ["carol"], "GET").status_code == 403
    assert _query_tickers_owners(_named_query(client, ["alice"], "GET")) == {"alice"}


# ------------------------------------------- disable_auth + ENFORCE_OWNER_ACCESS


@pytest.mark.parametrize("name", sorted(_ALL_OWNER_ROUTES))
def test_enforce_owner_access_filters_the_all_owners_path(accounts, builders, monkeypatch, name):
    client = _enforced_client(monkeypatch)

    assert _owners_seen(client, name) == _MINE


def test_enforce_owner_access_naming_an_unrelated_owner_is_403(accounts, builders, monkeypatch):
    client = _enforced_client(monkeypatch)

    resp = _named_query(client, ["bob"])

    assert resp.status_code == 403
    assert resp.json() == _FORBIDDEN
    assert _query_tickers_owners(_named_query(client, ["carol"])) == {"carol"}


# -------------------------------------------------- disable_auth, flag off


@pytest.mark.parametrize("name", sorted(_ALL_OWNER_ROUTES))
def test_flag_off_anonymous_still_sees_every_owner(accounts, builders, monkeypatch, name):
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", False)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)

    assert _owners_seen(client, name) == _EVERYONE
    assert _query_tickers_owners(_named_query(client, ["bob"])) == {"bob"}


def test_system_job_still_lists_every_owner_with_auth_enabled(accounts, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)

    assert list_portfolios() == []
    with auth.system_job_context():
        assert {pf["owner"] for pf in list_portfolios()} == _EVERYONE


# ------------------------------------------------------------- no cross-user leak


@pytest.mark.parametrize("name", sorted(_ALL_OWNER_ROUTES))
def test_results_do_not_leak_between_signed_in_users(accounts, builders, monkeypatch, name):
    """Same app and process: one user's results never reach the next user."""
    client = _signed_in_client(monkeypatch)
    me = dict(client.headers)
    bob = {"Authorization": f"Bearer {auth.create_access_token('bob@example.com')}"}

    assert _owners_seen(client, name) == _MINE
    client.headers.update(bob)
    assert _owners_seen(client, name) == {"bob"}
    client.headers.update(me)
    assert _owners_seen(client, name) == _MINE


@pytest.mark.parametrize("name", sorted(_ALL_OWNER_ROUTES))
def test_results_do_not_leak_between_users_under_the_flag(accounts, builders, monkeypatch, name):
    client = _enforced_client(monkeypatch)

    assert _owners_seen(client, name) == _MINE
    monkeypatch.setattr(config, "local_login_email", "bob@example.com", raising=False)
    assert _owners_seen(client, name) == {"bob"}


# ------------------------------------------------------------------ end to end


def test_end_to_end_custom_query_with_real_login(accounts, monkeypatch):
    """Nothing stubbed: real person.json, real holdings, real ``/token`` login."""
    client = _signed_in_client(monkeypatch)

    everything = client.post("/custom-query/run", json=_QUERY)
    assert everything.status_code == 200, everything.text
    tickers = {row["ticker"] for row in everything.json()["results"]}
    assert tickers == {_OWN_TICKER["alice"], _OWN_TICKER["carol"], _SHARED}

    denied = client.get(
        "/custom-query/run", params={"start": "2024-01-02", "end": _TODAY, "owners": "bob", "format": "csv"}
    )
    assert denied.status_code == 403
    assert _OWN_TICKER["bob"] not in denied.text
