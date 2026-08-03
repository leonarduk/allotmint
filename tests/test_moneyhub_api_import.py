import time

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import moneyhub_tokens
from backend.common.moneyhub_tokens import TokenSet
from backend.common.url_validator import InvalidExternalURLError
from backend.config import config
from backend.importers import moneyhub_api as moneyhub_mapper
from backend.integrations.moneyhub_api import MoneyhubAPIError, MoneyhubClient
from backend.routes import transactions

# ---------------------------------------------------------------------------
# backend.integrations.moneyhub_api.MoneyhubClient
# ---------------------------------------------------------------------------


def test_get_moneyhub_client_is_lazily_reused(monkeypatch):
    monkeypatch.setattr(transactions, "_moneyhub_client_instance", None)
    monkeypatch.setenv("MONEYHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("MONEYHUB_CLIENT_SECRET", "client-secret")

    first = transactions._get_moneyhub_client()
    second = transactions._get_moneyhub_client()

    assert first is second
    assert first.client_id == "client-id"
    assert first.client_secret == "client-secret"


@pytest.mark.parametrize("missing_name", ["MONEYHUB_CLIENT_ID", "MONEYHUB_CLIENT_SECRET"])
def test_get_moneyhub_client_requires_credentials(monkeypatch, missing_name):
    monkeypatch.setattr(transactions, "_moneyhub_client_instance", None)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("MONEYHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("MONEYHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.delenv(missing_name)

    with pytest.raises(
        RuntimeError, match="MONEYHUB_CLIENT_ID and MONEYHUB_CLIENT_SECRET must be set"
    ):
        transactions._get_moneyhub_client()


def test_app_startup_warns_but_succeeds_without_moneyhub_credentials(monkeypatch, caplog):
    """A missing credential pair must only disable the feature, not crash startup (#5729)."""
    monkeypatch.setattr(transactions, "_moneyhub_client_instance", None)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("MONEYHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("MONEYHUB_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    app = create_app()
    with caplog.at_level("WARNING", logger="transactions"):
        with TestClient(app):
            pass

    assert any("MONEYHUB_CLIENT_ID" in record.message for record in caplog.records)


def test_moneyhub_import_route_returns_503_when_unconfigured(monkeypatch):
    monkeypatch.setattr(transactions, "_moneyhub_client_instance", None)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("MONEYHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("MONEYHUB_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/transactions/import/moneyhub", data={"owner": "test-owner"})

    assert response.status_code == 503
    assert "MONEYHUB_CLIENT_ID" in response.json()["detail"]


def test_refresh_access_token_posts_expected_payload(monkeypatch):
    client = MoneyhubClient(client_id="id", client_secret="secret")
    called = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "new-token", "refresh_token": "new-refresh", "expires_in": 3600}

    def fake_post(url, data=None, timeout=None, **kwargs):
        called["url"] = url
        called["data"] = data
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    result = client.refresh_access_token("old-refresh")

    assert result["access_token"] == "new-token"
    assert called["url"] == "https://api.moneyhub.co.uk/oidc/token"
    assert called["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh",
        "client_id": "id",
        "client_secret": "secret",
    }


def test_refresh_access_token_wraps_network_error(monkeypatch):
    client = MoneyhubClient(client_id="id", client_secret="secret")

    def fake_post(*args, **kwargs):
        raise requests.RequestException("network error")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(MoneyhubAPIError, match="Token refresh failed"):
        client.refresh_access_token("old-refresh")


def test_fetch_transactions_returns_data_list(monkeypatch):
    client = MoneyhubClient(client_id="id", client_secret="secret")
    called = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"id": "tx-1"}, {"id": "tx-2"}]}

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        called["url"] = url
        called["params"] = params
        called["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    txs = client.fetch_transactions("access-token", account_id="acc-1")

    assert [t["id"] for t in txs] == ["tx-1", "tx-2"]
    assert called["params"] == {"accountId": "acc-1"}
    assert called["headers"] == {"Authorization": "Bearer access-token"}


def test_fetch_transactions_returns_bare_list_payload(monkeypatch):
    client = MoneyhubClient(client_id="id", client_secret="secret")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"id": "tx-1"}]

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
    txs = client.fetch_transactions("access-token")
    assert txs == [{"id": "tx-1"}]


@pytest.mark.parametrize(
    "payload",
    [
        {"data": None},
        {"data": "not-a-list"},
        {"data": [{"id": "tx-1"}, "not-an-object"]},
    ],
)
def test_fetch_transactions_rejects_invalid_payload(monkeypatch, payload):
    client = MoneyhubClient(client_id="id", client_secret="secret")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())

    with pytest.raises(MoneyhubAPIError, match="invalid payload"):
        client.fetch_transactions("access-token")


def test_fetch_transactions_wraps_network_error(monkeypatch):
    client = MoneyhubClient(client_id="id", client_secret="secret")

    def fake_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(MoneyhubAPIError, match="Transaction fetch failed"):
        client.fetch_transactions("access-token")


def test_client_rejects_private_base_url():
    client = MoneyhubClient(client_id="id", client_secret="secret", base_url="https://127.0.0.1")
    with pytest.raises(InvalidExternalURLError):
        client.fetch_transactions("access-token")


# ---------------------------------------------------------------------------
# backend.importers.moneyhub_api.map_transactions
# ---------------------------------------------------------------------------


def test_map_transactions_maps_fields():
    raw = [
        {
            "id": "tx-1",
            "accountId": "mh-acc-1",
            "date": "2024-05-01",
            "amount": {"amount": -42.50, "currency": "GBP"},
            "description": "Tesco Store",
            "category": "Groceries",
            "status": "posted",
        }
    ]
    txs = moneyhub_mapper.map_transactions(raw, "alice", account_id_map={"mh-acc-1": "Current"})

    assert len(txs) == 1
    tx = txs[0]
    assert tx.external_id == "moneyhub:tx-1"
    assert tx.owner == "alice"
    assert tx.account == "Current"
    assert tx.date == "2024-05-01"
    assert tx.amount_minor == -4250
    assert tx.currency == "GBP"
    assert tx.comments == "Tesco Store"
    assert tx.type == "Groceries"
    assert tx.kind == "account"
    assert tx.synthetic is False


def test_map_transactions_excludes_pending():
    raw = [
        {"id": "tx-1", "accountId": "a", "amount": {"amount": 1.0}, "status": "pending"},
        {"id": "tx-2", "accountId": "a", "amount": {"amount": 2.0}, "status": "posted"},
    ]
    txs = moneyhub_mapper.map_transactions(raw, "alice")
    assert [t.external_id for t in txs] == ["moneyhub:tx-2"]


def test_map_transactions_unmapped_account_id_falls_through():
    raw = [{"id": "tx-1", "accountId": "mh-unknown", "amount": {"amount": 1.0}}]
    txs = moneyhub_mapper.map_transactions(raw, "alice")
    assert txs[0].account == "mh-unknown"


def test_map_transactions_missing_amount_is_none():
    raw = [{"id": "tx-1", "accountId": "a"}]
    txs = moneyhub_mapper.map_transactions(raw, "alice")
    assert txs[0].amount_minor is None
    assert txs[0].currency is None


def test_map_transactions_non_numeric_amount_is_none():
    raw = [{"id": "tx-1", "accountId": "a", "amount": {"amount": "not-a-number"}}]
    txs = moneyhub_mapper.map_transactions(raw, "alice")
    assert txs[0].amount_minor is None


# ---------------------------------------------------------------------------
# backend.common.moneyhub_tokens
# ---------------------------------------------------------------------------


@pytest.fixture
def token_storage(tmp_path, monkeypatch):
    template = str(tmp_path / "{owner}.json")
    monkeypatch.setenv("MONEYHUB_TOKENS_STORAGE_URI", f"file://{template}")
    return template


def test_load_token_set_returns_none_when_absent(token_storage):
    assert moneyhub_tokens.load_token_set("alice") is None


def test_save_and_load_token_set_round_trips(token_storage):
    token_set = TokenSet(
        access_token="a", refresh_token="r", expires_at=123.0, account_ids=["acc-1"]
    )
    moneyhub_tokens.save_token_set("alice", token_set)

    loaded = moneyhub_tokens.load_token_set("alice")
    assert loaded == token_set


def test_get_valid_access_token_returns_cached_when_not_expired(token_storage):
    token_set = TokenSet(access_token="a", refresh_token="r", expires_at=time.time() + 3600)
    moneyhub_tokens.save_token_set("alice", token_set)

    client = MoneyhubClient(client_id="id", client_secret="secret")
    assert moneyhub_tokens.get_valid_access_token("alice", client) == "a"


def test_get_valid_access_token_refreshes_when_expired(token_storage, monkeypatch):
    token_set = TokenSet(access_token="stale", refresh_token="r", expires_at=time.time() - 10)
    moneyhub_tokens.save_token_set("alice", token_set)

    def fake_post(url, data=None, timeout=None, **kwargs):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"access_token": "fresh", "refresh_token": "r2", "expires_in": 3600}

        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    client = MoneyhubClient(client_id="id", client_secret="secret")
    token = moneyhub_tokens.get_valid_access_token("alice", client)

    assert token == "fresh"
    reloaded = moneyhub_tokens.load_token_set("alice")
    assert reloaded.access_token == "fresh"
    assert reloaded.refresh_token == "r2"


def test_get_valid_access_token_raises_when_no_token_stored(token_storage):
    client = MoneyhubClient(client_id="id", client_secret="secret")
    with pytest.raises(moneyhub_tokens.MoneyhubAuthError, match="No Moneyhub consent"):
        moneyhub_tokens.get_valid_access_token("alice", client)


def test_get_valid_access_token_raises_on_refresh_failure(token_storage, monkeypatch):
    token_set = TokenSet(access_token="stale", refresh_token="r", expires_at=time.time() - 10)
    moneyhub_tokens.save_token_set("alice", token_set)

    def fake_post(*args, **kwargs):
        raise requests.RequestException("rejected")

    monkeypatch.setattr(requests, "post", fake_post)
    client = MoneyhubClient(client_id="id", client_secret="secret")
    with pytest.raises(moneyhub_tokens.MoneyhubAuthError, match="token refresh failed"):
        moneyhub_tokens.get_valid_access_token("alice", client)


# ---------------------------------------------------------------------------
# /transactions/import/moneyhub route
# ---------------------------------------------------------------------------


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    template = str(tmp_path / "tokens" / "{owner}.json")
    monkeypatch.setenv("MONEYHUB_TOKENS_STORAGE_URI", f"file://{template}")
    app = create_app()
    return TestClient(app)


def test_import_moneyhub_route_requires_consent(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.post("/transactions/import/moneyhub", data={"owner": "alice"})
    assert resp.status_code == 424


def test_import_moneyhub_route_persists_and_dedupes_on_reimport(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    token_set = TokenSet(access_token="a", refresh_token="r", expires_at=time.time() + 3600)
    moneyhub_tokens.save_token_set("alice", token_set)

    raw_transactions = [
        {
            "id": "tx-1",
            "accountId": "Current",
            "date": "2024-05-01",
            "amount": {"amount": -42.50, "currency": "GBP"},
            "description": "Tesco Store",
            "category": "Groceries",
            "status": "posted",
        },
        {
            "id": "tx-2",
            "accountId": "Current",
            "date": "2024-05-02",
            "amount": {"amount": 1500.00, "currency": "GBP"},
            "description": "Salary",
            "category": "Income",
            "status": "posted",
        },
    ]

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": raw_transactions}

        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    resp = client.post("/transactions/import/moneyhub", data={"owner": "alice"})
    assert resp.status_code == 200
    first = resp.json()
    assert first["skipped"] == []
    assert {t["external_id"] for t in first["persisted"]} == {"moneyhub:tx-1", "moneyhub:tx-2"}
    assert all(t["owner"] == "alice" for t in first["persisted"])
    assert all(t["account"] == "Current" for t in first["persisted"])

    # Re-importing must not create duplicates.
    resp = client.post("/transactions/import/moneyhub", data={"owner": "alice"})
    assert resp.status_code == 200
    assert resp.json() == {"persisted": [], "skipped": []}


def test_import_moneyhub_route_surfaces_upstream_failure(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    token_set = TokenSet(access_token="a", refresh_token="r", expires_at=time.time() + 3600)
    moneyhub_tokens.save_token_set("alice", token_set)

    def fake_get(*args, **kwargs):
        raise requests.RequestException("upstream down")

    monkeypatch.setattr(requests, "get", fake_get)

    resp = client.post("/transactions/import/moneyhub", data={"owner": "alice"})
    assert resp.status_code == 502


def _make_auth_enabled_client(tmp_path, monkeypatch):
    """Build a client with authentication (and thus owner scoping) enabled.

    Mirrors ``_auth_enabled_client`` in ``tests/test_user_config_route.py``:
    ``disable_auth`` must be off before ``create_app()`` for both the
    router-level auth dependency and :func:`ensure_owner_access` to be live.
    """

    monkeypatch.setattr(config, "disable_auth", False)
    client = _make_client(tmp_path, monkeypatch)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_import_moneyhub_route_requires_owner_authorization(tmp_path, monkeypatch):
    """A logged-in user may only trigger a Moneyhub import for an authorized owner (#5704)."""

    def fake_meta(owner, root=None):
        return {"email": "user@example.com"} if owner == "alice" else {}

    monkeypatch.setattr("backend.common.authz.load_person_meta", fake_meta)
    client = _make_auth_enabled_client(tmp_path, monkeypatch)

    # Authorized owner: falls through to the normal consent check (no token stored yet).
    resp = client.post("/transactions/import/moneyhub", data={"owner": "alice"})
    assert resp.status_code == 424

    # Unauthorized owner: rejected before any Moneyhub call is attempted.
    resp = client.post("/transactions/import/moneyhub", data={"owner": "bob"})
    assert resp.status_code == 403
