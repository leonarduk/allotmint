"""Per-owner access on AWS behind ``ENFORCE_OWNER_ACCESS`` (#11087).

The backend Lambda runs with ``disable_auth`` (API Gateway does the sign-in),
which used to switch the owner/email/``viewers`` checks off as well. With
``config.enforce_owner_access`` on they run against the gateway-verified
identity; with it off (the default) nothing changes.

Synthetic owners only: ``xavier`` (``x@example.com``, viewer
``a@example.com``) and ``yolanda`` (``y@example.com``). User A is listed only
in xavier's ``viewers``. S3 is replaced by an in-memory provider so
``app_env="aws"`` exercises the real ``_list_aws_plots`` path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import jwt
import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.common import authz, data_loader, group_portfolio, portfolio_cache
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.routes import portfolio as portfolio_routes

X, Y, DEMO = "xavier", "yolanda", "buffett"
VIEWER_A = "a@example.com"
_PEOPLE: Dict[str, Dict[str, Any]] = {
    X: {"owner": X, "full_name": "Xavier", "email": "x@example.com", "viewers": [VIEWER_A]},
    Y: {"owner": Y, "full_name": "Yolanda", "email": "y@example.com"},
    DEMO: {"owner": DEMO, "full_name": "Buffett"},
}


class _FakeS3:
    """In-memory stand-in for ``S3DataProvider`` covering listing and person metadata."""

    def __init__(self, bucket: str | None = None) -> None:
        self.bucket = bucket

    def list_plots(self, current_user: str | None = None) -> List[Dict[str, Any]]:
        return [{"owner": owner, "accounts": ["isa"]} for owner in _PEOPLE]

    def load_person_meta(self, owner: str) -> SimpleNamespace:
        return SimpleNamespace(metadata=dict(_PEOPLE.get(owner, {})))


def _gateway_token(email: str | None = None, sub: str | None = None) -> str:
    """A Cognito-style ID token: not signed with our secret, so read from its claims.

    On AWS the gateway authorizer has verified the real token's signature
    before the Lambda runs (docs/AUTH.md "Deployed-gateway auth").
    """

    claims: Dict[str, Any] = {"token_use": "id", "exp": 4102444800}
    if email:
        claims["email"] = email
    if sub:
        claims["sub"] = sub
    return jwt.encode(claims, "gateway-signing-key-not-ours-32bytes!", algorithm="HS256")


def _as(identity: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {_gateway_token(email=identity)}"}


def _write_accounts(root: Path) -> None:
    for owner, person in _PEOPLE.items():
        (root / owner).mkdir()
        (root / owner / "person.json").write_text(json.dumps(person))
        (root / owner / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": []})
        )


def _portfolio_of(owner: str) -> Dict[str, Any]:
    return {"owner": owner, "accounts": [{"account_type": "isa", "owner": owner, "holdings": []}]}


@pytest.fixture
def aws_app(monkeypatch, tmp_path):
    """The real app as the Lambda runs it: ``app_env="aws"``, ``disable_auth`` on.

    Returns a function that sets ``enforce_owner_access`` and gives a client.
    """

    _write_accounts(tmp_path)
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setattr(data_loader, "S3DataProvider", _FakeS3)
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"x@example.com", "y@example.com", VIEWER_A})
    monkeypatch.setattr(
        portfolio_routes.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, accounts_root=None, pricing_date=None: _portfolio_of(owner),
    )
    # Every owner's portfolio, unfiltered: the group's membership (from
    # list_plots) is what has to narrow it.
    monkeypatch.setattr(
        "backend.common.portfolio_loader.list_portfolios",
        lambda: [_portfolio_of(owner) for owner in _PEOPLE],
    )
    app = create_app()
    # Patched after create_app(), whose config reload would otherwise overwrite it.
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "local_login_email", "")
    monkeypatch.setattr(config, "demo_link_enabled", True)
    monkeypatch.setattr(config, "demo_link_owner", DEMO)
    app.state.accounts_root = tmp_path

    def _client(enforce: bool) -> TestClient:
        monkeypatch.setattr(config, "enforce_owner_access", enforce)
        return TestClient(app)

    return _client


def _owners(client: TestClient, headers: Dict[str, str] | None = None) -> List[str]:
    resp = client.get("/owners", headers=headers or {})
    assert resp.status_code == 200
    return sorted(entry["owner"] for entry in resp.json())


def _all_group_members(client: TestClient, headers: Dict[str, str] | None = None) -> List[str]:
    resp = client.get("/groups", headers=headers or {})
    assert resp.status_code == 200
    return next(group["members"] for group in resp.json() if group["slug"] == "all")


def _group_owners(client: TestClient, headers: Dict[str, str] | None = None) -> List[str]:
    resp = client.get("/portfolio-group/all", headers=headers or {})
    assert resp.status_code == 200
    return sorted({account["owner"] for account in resp.json()["accounts"]})


# ---- flag on: the acceptance criteria ---------------------------------------


def test_viewer_of_x_is_denied_owner_y(aws_app):
    client = aws_app(enforce=True)

    denied = client.get(f"/portfolio/{Y}", headers=_as(VIEWER_A))
    allowed = client.get(f"/portfolio/{X}", headers=_as(VIEWER_A))

    assert denied.status_code == 403
    assert Y not in denied.text
    assert allowed.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        f"/portfolio/{Y}/sectors",
        f"/portfolio/{Y}/currencies",
        f"/portfolio/{Y}/look-through",
        f"/account/{Y}/isa",
    ],
)
def test_viewer_of_x_is_denied_owner_y_sub_routes(aws_app, path):
    assert aws_app(enforce=True).get(path, headers=_as(VIEWER_A)).status_code == 403


def test_viewer_of_x_does_not_see_y_in_owners_or_the_all_group(aws_app):
    client = aws_app(enforce=True)

    assert _owners(client, _as(VIEWER_A)) == [X]
    assert _all_group_members(client, _as(VIEWER_A)) == [X]
    assert _group_owners(client, _as(VIEWER_A)) == [X]


def test_owner_email_and_owner_id_are_still_allowed(aws_app):
    client = aws_app(enforce=True)
    by_id = {"Authorization": f"Bearer {_gateway_token(sub=Y)}"}

    assert client.get(f"/portfolio/{Y}", headers=_as("y@example.com")).status_code == 200
    assert client.get(f"/portfolio/{Y}", headers=by_id).status_code == 200
    assert _owners(client, _as("y@example.com")) == [Y]
    assert _owners(client, by_id) == [Y]


def test_identity_resolving_routes_deny_through_ensure_owner_access(aws_app):
    """``/user-config/{owner}`` takes identity from ``get_active_user`` (the #11047 pattern)."""
    client = aws_app(enforce=True)

    assert client.get(f"/user-config/{Y}", headers=_as(VIEWER_A)).status_code == 403
    assert client.get(f"/user-config/{X}", headers=_as(VIEWER_A)).status_code == 200


def test_anonymous_request_is_denied_and_lists_nobody(aws_app):
    """No identity with the flag on means no access -- never "every owner"."""
    client = aws_app(enforce=True)

    assert client.get(f"/portfolio/{X}").status_code == 403
    assert _owners(client) == []
    assert _all_group_members(client) == []
    assert _group_owners(client) == []


def test_unreadable_token_is_treated_as_no_identity(aws_app):
    client = aws_app(enforce=True)
    garbage = {"Authorization": "Bearer not-a-jwt"}

    assert client.get(f"/portfolio/{X}", headers=garbage).status_code == 403
    assert _owners(client, garbage) == []


def test_group_cache_does_not_leak_between_users(aws_app, monkeypatch):
    """The per-slug group cache is keyed by the caller under the flag."""
    client = aws_app(enforce=True)
    builds: List[str] = []
    real_build = group_portfolio.build_group_portfolio

    def _counting_build(slug, **kwargs):
        builds.append(slug)
        return real_build(slug, **kwargs)

    monkeypatch.setattr(portfolio_routes.group_portfolio, "build_group_portfolio", _counting_build)

    assert _group_owners(client, _as("y@example.com")) == [Y]
    assert _group_owners(client, _as(VIEWER_A)) == [X]
    assert _group_owners(client) == []
    # Repeat callers still share their own entry.
    assert _group_owners(client, _as(VIEWER_A)) == [X]
    assert _group_owners(client, _as("y@example.com")) == [Y]
    assert len(builds) == 3


def test_opportunities_group_cache_does_not_leak_between_users(aws_app, monkeypatch):
    """``/opportunities?group=`` caches per group too, so it takes the same scope."""
    from backend.routes import opportunities

    client = aws_app(enforce=True)
    monkeypatch.setattr(
        opportunities,
        "_group_opportunities",
        lambda slug, **_kw: {"gainers": [], "losers": [], "anomalies": group_portfolio.group_members(slug)},
    )

    def _anomalies_as(local_login: str) -> List[str]:
        # No bearer token, so the local login names the caller (resolve_gateway_identity).
        monkeypatch.setattr(config, "local_login_email", local_login)
        resp = client.get("/opportunities", params={"group": "all"})
        assert resp.status_code == 200
        return resp.json()["context"]["anomalies"]

    assert _anomalies_as("y@example.com") == [Y]
    assert _anomalies_as(VIEWER_A) == [X]


# ---- flag off: unchanged ------------------------------------------------------


def test_flag_off_aws_behaviour_is_unchanged(aws_app):
    client = aws_app(enforce=False)

    assert client.get(f"/portfolio/{Y}", headers=_as(VIEWER_A)).status_code == 200
    assert client.get(f"/user-config/{Y}", headers=_as(VIEWER_A)).status_code == 200
    assert set(_owners(client, _as(VIEWER_A))) >= {X, Y}
    assert set(_all_group_members(client, _as(VIEWER_A))) == {X, Y}
    assert _group_owners(client, _as(VIEWER_A)) == [X, Y]


def test_flag_off_local_anonymous_dev_is_unchanged(aws_app, monkeypatch):
    client = aws_app(enforce=False)
    monkeypatch.setattr(config, "app_env", "local")

    assert client.get(f"/portfolio/{Y}").status_code == 200
    assert {X, Y} <= set(_owners(client))
    assert set(_all_group_members(client)) == {X, Y}


@pytest.mark.parametrize("enforce", [False, True])
def test_demo_token_scoping_is_unchanged(aws_app, enforce):
    client = aws_app(enforce=enforce)
    demo = {"Authorization": f"Bearer {auth.create_demo_access_token(DEMO)}"}

    assert _owners(client, demo) == [DEMO]
    assert _all_group_members(client, demo) == [DEMO]
    assert client.get(f"/user-config/{Y}", headers=demo).status_code == 403


# ---- unit level ----------------------------------------------------------------


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(data_loader, "load_person_meta", lambda owner, root=None: dict(_PEOPLE.get(owner, {})))
    monkeypatch.setattr(authz, "load_person_meta", lambda owner, root=None: dict(_PEOPLE.get(owner, {})))


def test_ensure_owner_access_denies_a_non_viewer_when_enforced(enforced):
    authz.ensure_owner_access(VIEWER_A, X)
    authz.ensure_owner_access("Y@Example.com", Y)
    with pytest.raises(PermissionDeniedError):
        authz.ensure_owner_access(VIEWER_A, Y)


def test_ensure_owner_access_falls_back_to_the_request_identity(enforced):
    token = auth.current_user.set(VIEWER_A)
    try:
        authz.ensure_owner_access(None, X)
        with pytest.raises(PermissionDeniedError):
            authz.ensure_owner_access(None, Y)
    finally:
        auth.current_user.reset(token)


def test_ensure_owner_access_denies_anonymous_when_enforced(enforced):
    token = auth.current_user.set(None)
    try:
        with pytest.raises(PermissionDeniedError):
            authz.ensure_owner_access(None, X)
    finally:
        auth.current_user.reset(token)


def test_ensure_owner_access_still_no_ops_with_the_flag_off(enforced, monkeypatch):
    monkeypatch.setattr(config, "enforce_owner_access", False)
    authz.ensure_owner_access(None, Y)
    authz.ensure_owner_access(VIEWER_A, Y)


def test_ensure_request_owner_access_only_acts_when_enforced(enforced, monkeypatch):
    token = auth.current_user.set(VIEWER_A)
    try:
        with pytest.raises(PermissionDeniedError):
            authz.ensure_request_owner_access(Y)
        monkeypatch.setattr(config, "enforce_owner_access", False)
        authz.ensure_request_owner_access(Y)
    finally:
        auth.current_user.reset(token)


def test_flag_needs_disable_auth_to_matter(monkeypatch):
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "disable_auth", False)
    assert auth.owner_access_enforced_under_disable_auth() is False
    monkeypatch.setattr(config, "disable_auth", True)
    assert auth.owner_access_enforced_under_disable_auth() is True
    monkeypatch.setattr(config, "enforce_owner_access", False)
    assert auth.owner_access_enforced_under_disable_auth() is False


def test_access_scope_keys_users_apart_only_when_enforced(enforced, monkeypatch):
    token = auth.current_user.set(" A@Example.com ")
    try:
        assert portfolio_cache.access_scope() == ("user", VIEWER_A)
        auth.current_user.set(None)
        assert portfolio_cache.access_scope() == ("user", None)
        monkeypatch.setattr(config, "enforce_owner_access", False)
        assert portfolio_cache.access_scope() is None
    finally:
        auth.current_user.reset(token)


def test_access_scope_keeps_the_demo_scope_first(enforced, monkeypatch):
    monkeypatch.setattr(config, "demo_link_owner", DEMO)
    token = auth.demo_readonly.set(True)
    try:
        assert portfolio_cache.access_scope() == DEMO
    finally:
        auth.demo_readonly.reset(token)


def test_resolve_gateway_identity_never_raises():
    assert auth.resolve_gateway_identity(_gateway_token(email=VIEWER_A)) == VIEWER_A
    assert auth.resolve_gateway_identity(_gateway_token(sub=X)) == X
    assert auth.resolve_gateway_identity("not-a-jwt") is None
    assert auth.resolve_gateway_identity(auth.create_demo_access_token(DEMO)) is None
