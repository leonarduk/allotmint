"""Group routes follow the per-owner access rule (#10531).

A group's members are its configured members that the caller may see, by the
same owner/``email``/``viewers`` rule as ``/owners`` and ``ensure_owner_access``.
A group the caller can partly see returns only the visible members. A group
with no visible member is a 404 "Group not found" on every group route, the
same answer as an unknown slug, so it does not reveal that the group exists.
The ``all`` group ("At a glance") is the exception: it is everyone the caller
may see, and is empty, not missing, for a caller who may see nobody.

Before this, with auth enabled every group came back empty: ``list_groups``
listed owners with no user, which lists nobody.

These tests use real ``person.json`` and account files and a real ``POST
/token`` login (``user@example.com`` through the conftest Google stub). Nothing
in the group or portfolio build is stubbed. The owners are named after the
built-in groups (``backend.common.group_portfolio.list_groups``):

* ``adults`` = lucy + steve, ``children`` = alex + joe.
* The signed-in user is a viewer of steve only. bob@example.com owns lucy,
  alex and joe.

So the user sees ``all`` = [steve], ``adults`` = [steve] (lucy hidden), and no
``children`` group at all.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common import group_portfolio, instrument_api, portfolio_cache, portfolio_utils
from backend.config import config

_ME = "user@example.com"
_BOB = "bob@example.com"
_PEOPLE: Dict[str, Dict[str, Any]] = {
    "steve": {"owner": "steve", "email": "steve@example.com", "viewers": [_ME]},
    "lucy": {"owner": "lucy", "email": _BOB},
    "alex": {"owner": "alex", "email": _BOB},
    "joe": {"owner": "joe", "email": _BOB},
}
# A distinct cash balance per owner, so a response shows whose data it holds.
_CASH = {"steve": 1111.0, "lucy": 2222.0, "alex": 3333.0, "joe": 4444.0}

# Every group-scoped route, for a group slug.
_GROUP_ROUTES = [
    "/portfolio-group/{slug}",
    "/portfolio-group/{slug}/instruments",
    "/portfolio-group/{slug}/sectors",
    "/portfolio-group/{slug}/regions",
    "/portfolio-group/{slug}/currencies",
    "/portfolio-group/{slug}/look-through",
    "/portfolio-group/{slug}/exposure",
    "/portfolio-group/{slug}/movers",
    "/portfolio-group/{slug}/instrument/CASH.GBP",
    "/performance-group/{slug}",
    "/performance-group/{slug}/alpha",
    "/performance-group/{slug}/tracking-error",
    "/performance-group/{slug}/max-drawdown",
    "/performance-group/{slug}/risk-return",
    "/performance-group/{slug}/twr",
    "/performance-group/{slug}/xirr",
    "/fund-upkeep/group/{slug}/all-in-cost",
    "/opportunities?group={slug}",
]


@pytest.fixture(autouse=True)
def _fresh_caches():
    portfolio_cache.invalidate_group_portfolios()
    yield
    portfolio_cache.invalidate_group_portfolios()


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    """Real person.json and ISA files for every owner under a temp root."""
    # load_person_meta reads S3 when DATA_BUCKET is set (as in CI); keep it local.
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {_ME, _BOB})
    # There is no price history offline. Only the price lookups are stubbed:
    # movers and opportunities find no movers, and the performance series
    # find no closes (cash has none either), as for an unpriced portfolio.
    monkeypatch.setattr(instrument_api, "top_movers", lambda *a, **k: {"gainers": [], "losers": []})
    monkeypatch.setattr(instrument_api, "_price_and_changes", lambda ticker: {})
    monkeypatch.setattr(portfolio_utils, "_window_closes", lambda *a, **k: None)
    for owner, person in _PEOPLE.items():
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps(person))
        isa = {
            "owner": owner,
            "account_type": "ISA",
            "currency": "GBP",
            "holdings": [{"ticker": "CASH.GBP", "units": _CASH[owner], "cost_basis_gbp": _CASH[owner]}],
        }
        (tmp_path / owner / "isa.json").write_text(json.dumps(isa))
    return tmp_path


def _signed_in_client(monkeypatch) -> TestClient:
    """Auth enabled, signed in through the real ``/token`` endpoint as ``user@example.com``."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    resp = client.post("/token", json={"id_token": "good"})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _as(identity: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_access_token(identity)}"}


def _groups(client: TestClient, headers: Dict[str, str] | None = None) -> Dict[str, List[str]]:
    resp = client.get("/groups", headers=headers or {})
    assert resp.status_code == 200, resp.text
    return {g["slug"]: sorted(g["members"]) for g in resp.json()}


def _group_cash(client: TestClient, slug: str, headers: Dict[str, str] | None = None) -> Dict[str, float]:
    """Each owner's cash in ``/portfolio-group/{slug}``."""
    resp = client.get(f"/portfolio-group/{slug}", headers=headers or {})
    assert resp.status_code == 200, resp.text
    cash: Dict[str, float] = {}
    for account in resp.json()["accounts"]:
        for holding in account["holdings"]:
            if holding.get("ticker") == "CASH.GBP":
                cash[account["owner"]] = cash.get(account["owner"], 0.0) + float(holding["units"])
    return cash


# ───────────────────────────── auth enabled ─────────────────────────────


def test_groups_list_only_the_visible_members(accounts, monkeypatch):
    client = _signed_in_client(monkeypatch)

    assert _groups(client) == {"all": ["steve"], "adults": ["steve"]}


@pytest.mark.parametrize("slug", ["all", "adults"])
def test_group_portfolio_holds_only_the_visible_members_real_data(accounts, monkeypatch, slug):
    client = _signed_in_client(monkeypatch)

    assert _group_cash(client, slug) == {"steve": _CASH["steve"]}


@pytest.mark.parametrize("slug", ["all", "adults"])
def test_every_group_route_serves_a_visible_group(accounts, monkeypatch, slug):
    client = _signed_in_client(monkeypatch)

    for route in _GROUP_ROUTES:
        resp = client.get(route.format(slug=slug))

        assert resp.status_code == 200, (route, resp.text)
        for owner in ("lucy", "alex", "joe"):
            assert str(_CASH[owner]) not in resp.text, route


@pytest.mark.parametrize("slug", ["all", "adults"])
def test_group_aggregates_count_only_the_visible_members(accounts, monkeypatch, slug):
    client = _signed_in_client(monkeypatch)

    rows = client.get(f"/portfolio-group/{slug}/instruments").json()
    assert sum(float(r["market_value_gbp"] or 0) for r in rows) == pytest.approx(_CASH["steve"])
    cost = client.get(f"/fund-upkeep/group/{slug}/all-in-cost").json()
    assert {a["owner"] for a in cost["accounts"]} == {"steve"}
    # No member has a transaction ledger, so risk-return lists every member it covered.
    risk = client.get(f"/performance-group/{slug}/risk-return").json()
    assert risk["missing_members"] == ["steve"]


@pytest.mark.parametrize("slug", ["children", "no-such-group"])
def test_a_group_with_no_visible_member_is_not_found(accounts, monkeypatch, slug):
    """Same 404 as an unknown slug, so the group's existence does not leak."""
    client = _signed_in_client(monkeypatch)

    for route in _GROUP_ROUTES:
        resp = client.get(route.format(slug=slug))

        assert resp.status_code == 404, (route, resp.text)
        for owner in ("alex", "joe"):
            assert owner not in resp.text, route
            assert str(_CASH[owner]) not in resp.text, route


def test_anonymous_request_is_401(accounts, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    for path in ["/groups", *(route.format(slug="all") for route in _GROUP_ROUTES)]:
        assert client.get(path).status_code == 401, path


def test_owner_of_the_hidden_members_sees_them(accounts, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert _groups(client, _as(_BOB)) == {
        "all": ["alex", "joe", "lucy"],
        "adults": ["lucy"],
        "children": ["alex", "joe"],
    }
    assert _group_cash(client, "children", _as(_BOB)) == {"alex": _CASH["alex"], "joe": _CASH["joe"]}


def test_group_cache_does_not_leak_between_users_signed_in_in_turn(accounts, monkeypatch):
    client = _signed_in_client(monkeypatch)
    me = dict(client.headers)
    bob = _as(_BOB)

    assert _group_cash(client, "all", me) == {"steve": _CASH["steve"]}
    assert _group_cash(client, "all", bob) == {o: _CASH[o] for o in ("alex", "joe", "lucy")}
    assert _group_cash(client, "adults", bob) == {"lucy": _CASH["lucy"]}
    assert _group_cash(client, "adults", me) == {"steve": _CASH["steve"]}
    assert _group_cash(client, "all", me) == {"steve": _CASH["steve"]}
    assert client.get("/portfolio-group/children", headers=me).status_code == 404
    risk_bob = client.get("/performance-group/all/risk-return", headers=bob).json()
    risk_me = client.get("/performance-group/all/risk-return", headers=me).json()
    assert (risk_bob["missing_members"], risk_me["missing_members"]) == (["alex", "joe", "lucy"], ["steve"])
    opp_bob = client.get("/opportunities", params={"group": "children"}, headers=bob)
    opp_me = client.get("/opportunities", params={"group": "children"}, headers=me)
    assert (opp_bob.status_code, opp_me.status_code) == (200, 404)


def test_memoised_group_build_is_not_shared_between_users(accounts, monkeypatch):
    """The ``/performance-group`` routes share group builds (``memoised``), keyed by the caller too."""
    monkeypatch.setattr(config, "disable_auth", False)

    def build() -> Dict[str, Any]:
        return group_portfolio.build_group_portfolio("all")

    def owners_as(identity: str) -> List[str]:
        token = auth.current_user.set(identity)
        try:
            built = portfolio_cache.memoised(("portfolio", "all", True, None), build)
        finally:
            auth.current_user.reset(token)
        return sorted({a["owner"] for a in built["accounts"]})

    with portfolio_cache.sharing_performance_inputs():
        assert owners_as(_ME) == ["steve"]
        assert owners_as(_BOB) == ["alex", "joe", "lucy"]
        assert owners_as(_ME) == ["steve"]


# ───────────────────────────── other modes ─────────────────────────────


def _auth_disabled_client(monkeypatch, *, enforce: bool, local_login: str | None) -> TestClient:
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "enforce_owner_access", enforce)
    monkeypatch.setattr(config, "local_login_email", local_login, raising=False)
    return client


def test_flag_on_filters_groups_by_the_request_identity(accounts, monkeypatch):
    client = _auth_disabled_client(monkeypatch, enforce=True, local_login=_ME)

    assert _groups(client) == {"all": ["steve"], "adults": ["steve"]}
    assert _group_cash(client, "adults") == {"steve": _CASH["steve"]}
    assert client.get("/portfolio-group/children").status_code == 404
    assert client.get("/fund-upkeep/group/children/all-in-cost").status_code == 404


def test_flag_on_anonymous_sees_an_empty_all_group_and_nothing_else(accounts, monkeypatch):
    client = _auth_disabled_client(monkeypatch, enforce=True, local_login=None)

    assert _groups(client) == {"all": []}
    assert _group_cash(client, "all") == {}
    assert client.get("/portfolio-group/adults").status_code == 404


def test_flag_off_auth_disabled_is_unchanged(accounts, monkeypatch):
    client = _auth_disabled_client(monkeypatch, enforce=False, local_login=None)

    assert _groups(client) == {
        "all": ["alex", "joe", "lucy", "steve"],
        "adults": ["lucy", "steve"],
        "children": ["alex", "joe"],
    }
    assert _group_cash(client, "adults") == {"lucy": _CASH["lucy"], "steve": _CASH["steve"]}


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_sees_only_the_demo_owner(accounts, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "lucy", raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token('lucy')}"})

    assert _groups(client) == {"all": ["lucy"], "adults": ["lucy"]}
    assert _group_cash(client, "adults") == {"lucy": _CASH["lucy"]}
    assert client.get("/portfolio-group/children").status_code == 404


@pytest.mark.parametrize(("disable_auth", "enforce"), [(False, False), (True, True), (True, False)])
def test_system_job_sees_every_member(accounts, monkeypatch, disable_auth, enforce):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    monkeypatch.setattr(config, "enforce_owner_access", enforce)
    token = auth.current_user.set(None)
    try:
        with auth.system_job_context():
            groups = {g["slug"]: sorted(g["members"]) for g in group_portfolio.list_groups()}
            built = group_portfolio.build_group_portfolio("children")
    finally:
        auth.current_user.reset(token)

    assert groups["children"] == ["alex", "joe"]
    assert sorted({a["owner"] for a in built["accounts"]}) == ["alex", "joe"]
