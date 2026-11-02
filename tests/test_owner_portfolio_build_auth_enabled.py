"""``build_owner_portfolio`` finds the owner's plot with auth enabled (#11358).

``build_owner_portfolio`` looked the owner up with ``list_plots(accounts_root)``
and no user. With auth enabled that lists nobody, so every build raised
``FileNotFoundError`` and ``GET /portfolio/<owner>`` was 404 "Owner not found",
even for the caller's own portfolio and after the route's owner check passed.

The lookup is now filtered as the identity bound to the request, by the same
rule ``ensure_owner_access`` applies, so it never builds an owner the signed-in
user may not read. The end-to-end tests below use real ``person.json`` files,
real account files and a real ``POST /token`` login (``user@example.com`` via
the conftest Google stub), with nothing in the portfolio build stubbed.
"""

from __future__ import annotations

import json
from typing import Callable, Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_cache
from backend.config import config
from backend.routes import instrument as instrument_routes

_ME = "user@example.com"
# alice: the signed-in user's own owner (by email); carol: lists them as a
# viewer; bob: no relation, so every bob request must be denied.
_PEOPLE = {
    "alice": {"owner": "alice", "email": _ME},
    "bob": {"owner": "bob", "email": "bob@example.com"},
    "carol": {"owner": "carol", "email": "carol@example.com", "viewers": [_ME]},
}
# Distinct cash balance per owner, so a 200 proves whose data came back.
_CASH = {"alice": 1111.0, "bob": 2222.0, "carol": 3333.0}


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    """Real person.json and ISA files for alice, bob and carol under a temp root."""
    # load_person_meta reads S3 when DATA_BUCKET is set (as in CI); keep it local.
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
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
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _cash_units(payload: dict) -> list[float]:
    return [
        float(h["units"])
        for account in payload["accounts"]
        for h in account["holdings"]
        if h.get("ticker") == "CASH.GBP"
    ]


# ───────────────────────────── end to end ─────────────────────────────


@pytest.mark.parametrize("owner", ["alice", "carol"])
def test_owner_and_viewer_get_their_real_portfolio(accounts, monkeypatch, owner):
    client = _signed_in_client(monkeypatch)

    resp = client.get(f"/portfolio/{owner}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["owner"] == owner
    assert [a["account_type"] for a in body["accounts"]] == ["ISA"]
    assert _cash_units(body) == [_CASH[owner]]


@pytest.mark.parametrize("owner", ["alice", "carol"])
@pytest.mark.parametrize("suffix", ["sectors", "currencies", "look-through"])
def test_owner_and_viewer_get_portfolio_sub_routes(accounts, monkeypatch, owner, suffix):
    client = _signed_in_client(monkeypatch)

    resp = client.get(f"/portfolio/{owner}/{suffix}")

    assert resp.status_code == 200, resp.text
    assert resp.json(), resp.text


@pytest.mark.parametrize(
    "path",
    ["/portfolio/bob", "/portfolio/bob/sectors", "/portfolio/bob/currencies", "/portfolio/bob/look-through"],
)
def test_non_viewer_still_gets_403(accounts, monkeypatch, path):
    client = _signed_in_client(monkeypatch)

    resp = client.get(path)

    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": "Not authorized for this owner"}
    assert str(_CASH["bob"]) not in resp.text


def test_scenario_fx_returns_the_callers_owners_with_real_data(accounts, monkeypatch):
    """``/scenario/fx`` builds each visible owner's portfolio (#11355), now found with auth enabled."""
    client = _signed_in_client(monkeypatch)

    resp = client.get("/scenario/fx", params={"currency": "USD", "pct": -10})

    assert resp.status_code == 200, resp.text
    baselines = {row["owner"]: row["baseline_total_value_gbp"] for row in resp.json()}
    assert baselines == {"alice": _CASH["alice"], "carol": _CASH["carol"]}


def test_instrument_positions_return_the_callers_owners_with_real_data(accounts, monkeypatch):
    """``/instrument/`` positions come from real owner builds; only the price history is stubbed."""
    monkeypatch.setattr(instrument_routes, "load_meta_timeseries_range", lambda *a, **k: pd.DataFrame())
    client = _signed_in_client(monkeypatch)

    resp = client.get("/instrument/", params={"ticker": "CASH.GBP", "format": "json"})

    assert resp.status_code == 200, resp.text
    units = {p["owner"]: p["units"] for p in resp.json()["positions"]}
    assert units == {"alice": _CASH["alice"], "carol": _CASH["carol"]}


def test_anonymous_request_is_still_401(accounts, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert client.get("/portfolio/alice").status_code == 401


def test_one_session_reads_only_its_own_owners(accounts, monkeypatch):
    client = _signed_in_client(monkeypatch)

    assert _cash_units(client.get("/portfolio/alice").json()) == [_CASH["alice"]]
    assert _cash_units(client.get("/portfolio/carol").json()) == [_CASH["carol"]]
    assert client.get("/portfolio/bob").status_code == 403
    # A different user signed in afterwards sees their own owner, not the first user's.
    other = TestClient(create_app())
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {_ME, "bob@example.com"})
    bob_token = auth.create_access_token("bob@example.com")
    other.headers.update({"Authorization": f"Bearer {bob_token}"})
    assert _cash_units(other.get("/portfolio/bob").json()) == [_CASH["bob"]]
    assert other.get("/portfolio/alice").status_code == 403


def test_auth_disabled_anonymous_build_unchanged(accounts, monkeypatch):
    """``disable_auth`` with ``ENFORCE_OWNER_ACCESS`` off: every owner builds, as before."""
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", False)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)

    for owner in _PEOPLE:
        resp = client.get(f"/portfolio/{owner}")
        assert resp.status_code == 200, resp.text
        assert _cash_units(resp.json()) == [_CASH[owner]]


def test_enforce_owner_access_flag_unchanged(accounts, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", _ME, raising=False)

    assert _cash_units(client.get("/portfolio/alice").json()) == [_CASH["alice"]]
    assert _cash_units(client.get("/portfolio/carol").json()) == [_CASH["carol"]]
    assert client.get("/portfolio/bob").status_code == 403


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_is_confined_to_the_demo_owner(accounts, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "alice", raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token('alice')}"})

    resp = client.get("/portfolio/alice")
    assert resp.status_code == 200, resp.text
    assert _cash_units(resp.json()) == [_CASH["alice"]]
    assert client.get("/portfolio/carol").status_code == 403
    assert client.get("/portfolio/bob").status_code == 403


# ───────────────────────────── the lookup itself ─────────────────────────────


@pytest.fixture
def bound_identity() -> Iterator[Callable[[str | None], None]]:
    """Bind ``auth.current_user`` as a request would, and restore it afterwards."""
    tokens = []

    def _bind(identity: str | None) -> None:
        tokens.append(auth.current_user.set(identity))

    yield _bind
    for token in reversed(tokens):
        auth.current_user.reset(token)


def _owners(accounts_root) -> set[str]:
    return {p.owner for p in portfolio_mod._owner_plots(accounts_root)}


def test_lookup_with_auth_enabled_is_scoped_to_the_request_identity(accounts, monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", False)
    bound_identity(_ME)

    assert _owners(accounts) == {"alice", "carol"}
    assert portfolio_mod.build_owner_portfolio("alice", accounts)["owner"] == "alice"


def test_build_refuses_an_owner_the_request_identity_cannot_read(accounts, monkeypatch, bound_identity):
    """Defence in depth: a caller that skipped ``ensure_owner_access`` still cannot build bob."""
    monkeypatch.setattr(config, "disable_auth", False)
    bound_identity(_ME)

    with pytest.raises(FileNotFoundError):
        portfolio_mod.build_owner_portfolio("bob", accounts)


def test_lookup_with_auth_enabled_and_no_identity_lists_nobody(accounts, monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", False)
    bound_identity(None)

    assert _owners(accounts) == set()
    with pytest.raises(FileNotFoundError):
        portfolio_mod.build_owner_portfolio("alice", accounts)


def test_system_job_with_auth_enabled_still_builds_every_owner(accounts, monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", False)
    bound_identity(None)

    with auth.system_job_context():
        assert _owners(accounts) == set(_PEOPLE)
        assert portfolio_mod.build_owner_portfolio("bob", accounts)["owner"] == "bob"


def test_lookup_with_auth_disabled_ignores_a_bound_identity(accounts, monkeypatch, bound_identity):
    """``disable_auth`` without the flag never filtered this lookup, identity or not."""
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    bound_identity(_ME)

    assert _owners(accounts) == set(_PEOPLE)


def test_lookup_under_the_flag_still_filters_by_identity(accounts, monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", True)
    bound_identity(_ME)

    assert _owners(accounts) == {"alice", "carol"}


# ───────────────────────────── caches ─────────────────────────────


def test_access_scope_names_the_identity_with_auth_enabled(monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", False)
    bound_identity(" User@Example.com ")
    assert portfolio_cache.access_scope() == ("user", _ME)
    bound_identity(None)
    assert portfolio_cache.access_scope() == ("user", None)


def test_access_scope_unchanged_with_auth_disabled_and_flag_off(monkeypatch, bound_identity):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    bound_identity(_ME)
    assert portfolio_cache.access_scope() is None


def test_memoised_owner_build_is_not_shared_between_users(accounts, monkeypatch, bound_identity):
    """A performance build memoised for alice's user is never served to another identity."""
    monkeypatch.setattr(config, "disable_auth", False)
    portfolio_cache.invalidate_performance_inputs()
    key = ("portfolio", "alice", False, None)

    def build() -> dict:
        return portfolio_mod.build_owner_portfolio("alice", accounts)

    try:
        with portfolio_cache.sharing_performance_inputs():
            bound_identity(_ME)
            assert portfolio_cache.memoised(key, build)["owner"] == "alice"
            bound_identity("bob@example.com")
            with pytest.raises(FileNotFoundError):
                portfolio_cache.memoised(key, build)
    finally:
        portfolio_cache.invalidate_performance_inputs()
