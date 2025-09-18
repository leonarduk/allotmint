"""Tests for the approvals route covering success and error paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import backend.routes.approvals as approvals


def make_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(approvals.router)
    app.state.accounts_root = tmp_path
    return TestClient(app, raise_server_exceptions=False)


def test_get_approvals_success(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    (tmp_path / "bob" / "approvals.json").write_text(
        json.dumps({"approvals": [{"ticker": "ADM.L", "approved_on": "2024-06-04"}]}, indent=2)
    )
    client = make_client(tmp_path)
    resp = client.get("/accounts/bob/approvals")
    assert resp.status_code == 200
    assert resp.json() == {
        "approvals": [{"ticker": "ADM.L", "approved_on": "2024-06-04"}]
    }


def test_post_approval_request_success(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    resp = client.post("/accounts/bob/approval-requests", json={"ticker": "adm.l"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["requests"][0]["ticker"] == "ADM.L"
    assert "requested_on" in data["requests"][0]
    saved = json.loads((tmp_path / "bob" / "approval_requests.json").read_text())
    assert saved["requests"][0]["ticker"] == "ADM.L"


def test_post_approval_request_missing_ticker(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    resp = client.post("/accounts/bob/approval-requests", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "ticker is required"


def test_post_approval_request_missing_owner(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    resp = client.post("/accounts/missing/approval-requests", json={"ticker": "ADM.L"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}


def test_post_approval_request_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)

    def bad_write(self: Path, *args, **kwargs):
        raise OSError("no space left")

    monkeypatch.setattr(Path, "write_text", bad_write)
    resp = client.post("/accounts/bob/approval-requests", json={"ticker": "ADM.L"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "no space left"


@pytest.mark.parametrize(
    "payload, detail",
    [
        ({}, "approved_on is required"),
        ({"approved_on": "not-a-date"}, "invalid approved_on"),
    ],
)
def test_post_approval_invalid_or_missing_approved_on(
    tmp_path: Path, payload: dict[str, str], detail: str
) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    data = {"ticker": "ADM.L", **payload}
    resp = client.post("/accounts/bob/approvals", json=data)
    assert resp.status_code == 400
    assert resp.json()["detail"] == detail


def test_post_approval_success(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    resp = client.post(
        "/accounts/bob/approvals", json={"ticker": "adm.l", "approved_on": "2024-06-04"}
    )
    assert resp.status_code == 200
    assert resp.json()["approvals"] == [
        {"ticker": "ADM.L", "approved_on": "2024-06-04"}
    ]


def test_post_approval_missing_owner(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    resp = client.post(
        "/accounts/missing/approvals", json={"ticker": "ADM.L", "approved_on": "2024-06-04"}
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}


def test_post_approval_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("db down")

    monkeypatch.setattr(approvals, "upsert_approval", boom)
    resp = client.post(
        "/accounts/bob/approvals", json={"ticker": "ADM.L", "approved_on": "2024-06-04"}
    )
    assert resp.status_code == 500
    assert "Internal Server Error" in resp.text


def test_delete_approval_route_success(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    client.post(
        "/accounts/bob/approvals", json={"ticker": "ADM.L", "approved_on": "2024-06-04"}
    )
    resp = client.request("DELETE", "/accounts/bob/approvals", json={"ticker": "ADM.L"})
    assert resp.status_code == 200
    assert resp.json()["approvals"] == []


def test_delete_approval_route_nonexistent_ticker(tmp_path: Path) -> None:
    (tmp_path / "bob").mkdir()
    client = make_client(tmp_path)
    client.post(
        "/accounts/bob/approvals", json={"ticker": "ADM.L", "approved_on": "2024-06-04"}
    )
    resp = client.request("DELETE", "/accounts/bob/approvals", json={"ticker": "XYZ"})
    assert resp.status_code == 200
    assert resp.json()["approvals"] == [
        {"ticker": "ADM.L", "approved_on": "2024-06-04"}
    ]


def test_delete_approval_missing_owner(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    resp = client.request("DELETE", "/accounts/missing/approvals", json={"ticker": "ADM.L"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Owner not found"}


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows case-insensitive filesystem")
def test_post_approval_request_case_insensitive_root(tmp_path: Path) -> None:
    root = tmp_path / "RealRoot"
    owner = "bob"
    root.mkdir()
    (root / owner).mkdir()
    client = make_client(root)
    mixed_case_root = Path(root.parent / root.name.upper())
    client.app.state.accounts_root = mixed_case_root
    resp = client.post(f"/accounts/{owner}/approval-requests", json={"ticker": "ADM.L"})
    assert resp.status_code == 200

