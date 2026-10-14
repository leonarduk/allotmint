"""Future-dated transactions are rejected on every write path (#10898).

The manual-holding path already refused a date more than a day ahead; create,
update and import now apply the same rule, since the holdings rebuild would
otherwise count the trade in today's holdings.
"""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import importers
from backend.app import create_app
from backend.config import config
from backend.routes.transactions import Transaction

TOO_FAR = (date.today() + timedelta(days=2)).isoformat()
# One day of slack covers a browser whose local date is ahead of the server's.
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


def _payload(**overrides):
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "PFE",
        "date": "2024-05-01",
        "price_gbp": 10.5,
        "units": 2,
        "reason": "diversify",
    }
    payload.update(overrides)
    return payload


def _stored(tmp_path):
    return json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]


def test_create_rejects_future_date(client, tmp_path):
    resp = client.post("/transactions", json=_payload(date=TOO_FAR))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date cannot be in the future"
    assert not list((tmp_path / "alice").glob("*_transactions.json"))


def test_create_allows_one_day_of_slack(client):
    assert client.post("/transactions", json=_payload(date=TOMORROW)).status_code == 201


def test_update_rejects_future_date(client, tmp_path):
    created = client.post("/transactions", json=_payload()).json()
    resp = client.put(f"/transactions/{created['id']}", json=_payload(date=TOO_FAR))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date cannot be in the future"
    assert [tx["date"] for tx in _stored(tmp_path)] == ["2024-05-01"]


def test_import_skips_future_rows_and_keeps_historical(client, tmp_path, monkeypatch):
    rows = [
        Transaction(owner="alice", account="ISA", date="2024-05-01", ticker="PFE", type="BUY", price=10.5, units=2),
        Transaction(owner="alice", account="ISA", date=TOO_FAR, ticker="PFE", type="BUY", price=10.5, units=1),
    ]
    monkeypatch.setattr(importers, "parse", lambda provider, data: rows)

    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves"},
        files={"file": ("tx.csv", b"unused", "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert [row["date"] for row in data["persisted"]] == ["2024-05-01"]
    assert [(row["date"], row["skip_reason"]) for row in data["skipped"]] == [(TOO_FAR, "date cannot be in the future")]
    assert [tx["date"] for tx in _stored(tmp_path)] == ["2024-05-01"]


def test_update_allows_one_day_of_slack(client, tmp_path):
    created = client.post("/transactions", json=_payload()).json()
    assert client.put(f"/transactions/{created['id']}", json=_payload(date=TOMORROW)).status_code == 200
    assert [tx["date"] for tx in _stored(tmp_path)] == [TOMORROW]


def test_import_of_only_future_rows_writes_nothing(client, tmp_path, monkeypatch):
    row = Transaction(owner="alice", account="ISA", date=TOO_FAR, ticker="PFE", type="BUY", price=10.5, units=1)
    monkeypatch.setattr(importers, "parse", lambda provider, data: [row])

    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves"},
        files={"file": ("tx.csv", b"unused", "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["persisted"] == []
    assert [r["skip_reason"] for r in resp.json()["skipped"]] == ["date cannot be in the future"]
    assert not list((tmp_path / "alice").glob("*_transactions.json"))
