"""GET /bots/digest/{owner}/... (#10485). Synthetic data only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bots import digest_store
from backend.bots.digest_models import BotRunRecord, Digest, DigestEntry, DigestItem, Severity
from backend.common.errors import OwnerNotFoundError, PermissionDeniedError
from backend.config import config
from backend.routes import bots_digest as route

NOW = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)


def _entry(key, owner="alex", status="new"):
    return DigestEntry(
        id=key,
        bot="cash",
        owner=owner,
        severity=Severity.HIGH,
        title=f"{key} title",
        created=NOW,
        dedupe_key=key,
        status=status,
    )


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    accounts = tmp_path / "accounts"
    for owner in ("alex", "bob"):
        (accounts / owner).mkdir(parents=True)
        (accounts / owner / "person.json").write_text(json.dumps({"owner": owner}))
    monkeypatch.setenv("BOTS_DIGESTS_URI", str(tmp_path / "digests"))
    monkeypatch.setenv("BOTS_RUNS_URI", str(tmp_path / "runs"))
    monkeypatch.setenv("BOTS_DIGEST_SETTINGS_URI", f"file://{tmp_path / 'settings.json'}")
    return tmp_path


def _client(data_root):
    app = FastAPI()
    app.include_router(route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app)


def _save(owner="alex", day=0, items=None):
    digest = Digest(
        owner=owner,
        generated_at=NOW + timedelta(days=day),
        opener="1 item needs you.",
        items=items if items is not None else [_entry(f"{owner}:k{day}", owner=owner)],
    )
    digest_store.save_digest(digest)
    return digest


def test_latest_returns_stored_digest(data_root):
    _save(day=0)
    _save(day=7)
    body = _client(data_root).get("/bots/digest/alex/latest").json()
    assert body["owner"] == "alex"
    assert [i["dedupe_key"] for i in body["items"]] == ["alex:k7"]
    assert body["needs_owner"] is True
    assert "open_keys" not in body


def test_latest_404_when_no_digest_yet(data_root):
    resp = _client(data_root).get("/bots/digest/alex/latest")
    assert resp.status_code == 404


def test_history_newest_first_and_limited(data_root):
    for day in (0, 7, 14):
        _save(day=day)
    body = _client(data_root).get("/bots/digest/alex/history?limit=2").json()
    assert [d["generated_at"][:10] for d in body["digests"]] == ["2026-10-26", "2026-10-19"]


def test_unknown_owner(data_root):
    with pytest.raises(OwnerNotFoundError):
        _client(data_root).get("/bots/digest/nobody/latest")


@pytest.fixture()
def auth_on(monkeypatch):
    from backend.common import authz

    monkeypatch.setattr(authz.config, "disable_auth", False, raising=False)
    monkeypatch.setattr(config, "allowed_emails", ["admin@example.com"], raising=False)


def _as(client, identity):
    from backend.auth import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: identity
    return client


def test_other_owner_cannot_read_digest(data_root, auth_on):
    _save()
    client = _as(_client(data_root), "bob")
    with pytest.raises(PermissionDeniedError):
        client.get("/bots/digest/alex/latest")
    with pytest.raises(PermissionDeniedError):
        client.get("/bots/digest/alex/history")
    with pytest.raises(PermissionDeniedError):
        client.get("/bots/digest/alex/preview")
    assert _as(client, "alex").get("/bots/digest/alex/latest").status_code == 200


def test_system_items_hidden_from_non_admins(data_root, auth_on):
    _save(items=[_entry("alex:own"), _entry("steward:system", owner=None)])
    client = _as(_client(data_root), "alex")
    keys = [i["dedupe_key"] for i in client.get("/bots/digest/alex/latest").json()["items"]]
    assert keys == ["alex:own"]
    assert route.is_admin("admin@example.com") is True
    assert route.is_admin("alex") is False


def test_preview_composes_without_writing(data_root):
    runs = data_root / "runs" / "cash-deployment"
    runs.mkdir(parents=True)
    record = BotRunRecord(
        bot_id="cash-deployment",
        status="ok",
        started_at=NOW,
        digest_items=[
            DigestItem(
                id="t3",
                bot="cash-deployment",
                owner="alex",
                severity=Severity.MEDIUM,
                title="Tranche 3 due Monday",
                created=NOW,
                dedupe_key="cash:t3",
            ),
            DigestItem(
                id="b1", bot="cash-deployment", owner="bob", title="Bob's item", created=NOW, dedupe_key="cash:b1"
            ),
        ],
    )
    (runs / "latest.json").write_text(record.model_dump_json())

    body = _client(data_root).get("/bots/digest/alex/preview").json()
    assert [i["dedupe_key"] for i in body["items"]] == ["cash:t3"]
    states = {b["bot"]: b["state"] for b in body["bots"]}
    assert states["cash-deployment"] == "ok"
    assert states["data-steward"] == "not_run_yet"
    assert not (data_root / "digests").exists()
