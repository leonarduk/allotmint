"""/allowance-guardian/{owner} routes (#10479). Synthetic owners and figures."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.allowance_guardian import report
from backend.common.errors import OwnerNotFoundError
from backend.routes import allowance_guardian as guardian_route

SCHEDULE = {
    "contributions": [
        {
            "account": "sipp",
            "amount_minor": 250_000,
            "frequency": "monthly",
            "source": "employer",
            "expected_day": 28,
            "start_date": "2026-04-28",
            "label": "Salary sacrifice",
        }
    ]
}


@pytest.fixture()
def data_root(monkeypatch, tmp_path):
    for owner in ("alex", "bob"):
        (tmp_path / "accounts" / owner).mkdir(parents=True)
    monkeypatch.setattr(report, "_owner_transactions", lambda owner: [])
    monkeypatch.setattr(report, "_pro_allowances", lambda: None)
    return tmp_path


def _client(data_root, raise_server_exceptions=True):
    app = FastAPI()
    app.include_router(guardian_route.router)
    app.state.accounts_root = data_root / "accounts"
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_schedule_defaults_to_empty(data_root):
    resp = _client(data_root).get("/allowance-guardian/alex/schedule")
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alex", "contributions": []}


def test_put_then_get_schedule_round_trip(data_root):
    client = _client(data_root)
    resp = client.put("/allowance-guardian/alex/schedule", json=SCHEDULE)
    assert resp.status_code == 200, resp.text
    assert (data_root / "contribution_schedules" / "alex.json").exists()
    body = client.get("/allowance-guardian/alex/schedule").json()
    assert body["owner"] == "alex"
    assert body["contributions"][0]["amount_minor"] == 250_000
    assert body["contributions"][0]["source"] == "employer"


@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({"contributions": [{**SCHEDULE["contributions"][0], "amount_minor": -1}]}, "amount_minor"),
        ({"contributions": [{**SCHEDULE["contributions"][0], "source": "lottery"}]}, "source"),
        ({"contributions": [{**SCHEDULE["contributions"][0], "account": "isa"}]}, "ISA"),
        ({**SCHEDULE, "owner": "bob"}, "does not match"),
    ],
)
def test_invalid_schedule_is_400(data_root, payload, fragment):
    resp = _client(data_root).put("/allowance-guardian/alex/schedule", json=payload)
    assert resp.status_code == 400
    assert fragment in resp.json()["detail"]


def test_report_uses_saved_schedule_and_always_carries_guardrails(data_root):
    client = _client(data_root)
    assert client.put("/allowance-guardian/alex/schedule", json=SCHEDULE).status_code == 200
    body = client.get("/allowance-guardian/alex").json()
    assert body["owner"] == "alex"
    assert body["schedule_count"] == 1
    assert body["contributions"]["results"], "expected contributions since 6 April are checked"
    assert len(body["not_modelled"]) == 3
    assert "regulated financial adviser" in body["adviser_note"]
    assert body["pension_allowance"]["available"] is False


def test_corrupt_saved_schedule_is_422(data_root):
    path = data_root / "contribution_schedules" / "alex.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"owner": "alex", "contributions": [{"account": "sipp"}]}', encoding="utf-8")
    resp = _client(data_root).get("/allowance-guardian/alex")
    assert resp.status_code == 422
    assert "Saved schedule for alex is invalid" in resp.json()["detail"]


def test_unknown_owner_is_not_found(data_root):
    with pytest.raises(OwnerNotFoundError):
        _client(data_root).get("/allowance-guardian/nobody/schedule")
