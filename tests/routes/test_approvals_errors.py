from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import backend.routes.approvals as approvals


def make_client(tmp_path) -> TestClient:
    app = FastAPI()
    app.include_router(approvals.router)
    app.state.accounts_root = tmp_path
    return TestClient(app)


def test_post_approval_request_missing_ticker(tmp_path):
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    resp = client.post("/accounts/bob/approval-requests", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "ticker is required"


@pytest.mark.parametrize(
    "payload, detail",
    [
        ({}, "approved_on is required"),
        ({"approved_on": "not-a-date"}, "invalid approved_on"),
    ],
)
def test_post_approval_invalid_or_missing_approved_on(tmp_path, payload, detail):
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    data = {"ticker": "ADM.L", **payload}
    resp = client.post("/accounts/bob/approvals", json=data)
    assert resp.status_code == 400
    assert resp.json()["detail"] == detail


def test_delete_approval_route_nonexistent_ticker(tmp_path):
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    resp = client.post(
        "/accounts/bob/approvals", json={"ticker": "ADM.L", "approved_on": "2024-06-04"}
    )
    assert resp.status_code == 200
    resp = client.request(
        "DELETE", "/accounts/bob/approvals", json={"ticker": "XYZ"}
    )
    assert resp.status_code == 200
    assert resp.json()["approvals"] == [
        {"ticker": "ADM.L", "approved_on": "2024-06-04"}
    ]
