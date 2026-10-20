"""Support-page data sync with allotmint-data (#11037)."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import auth
from backend.routes import data_sync
from backend.routes.data_sync import router

OWNER = "owner@example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    data_sync._token_cache.clear()
    monkeypatch.setenv("DATA_SYNC_REPO", "leonarduk/allotmint-data")
    monkeypatch.setenv("DATA_SYNC_GITHUB_TOKEN", "gh-token")
    # The deployed Lambda: DISABLE_AUTH is always set (API Gateway signs in).
    monkeypatch.setattr(data_sync.config, "disable_auth", True)
    monkeypatch.setattr(data_sync.config, "app_env", "aws")
    monkeypatch.setattr(data_sync.config, "allowed_emails", [OWNER])
    monkeypatch.setattr(data_sync.auth, "is_demo_request", lambda: False)
    yield
    data_sync._token_cache.clear()


def _client(identity):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.get_active_user] = lambda: identity
    return TestClient(app)


def _response(status, body=None):
    response = MagicMock()
    response.status_code = status
    response.ok = 200 <= status < 300
    response.json.return_value = body or {}
    return response


def _runs(status="completed", conclusion="success"):
    return _response(
        200,
        {
            "workflow_runs": [
                {
                    "status": status,
                    "conclusion": conclusion,
                    "html_url": "https://github.com/leonarduk/allotmint-data/actions/runs/1",
                    "created_at": "2026-10-20T21:00:00Z",
                    "triggering_actor": {"login": "leonarduk"},
                }
            ]
        },
    )


@pytest.fixture()
def github(monkeypatch):
    calls = []
    responses = {}

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        for (want_method, fragment), response in responses.items():
            if method == want_method and fragment in url:
                return response
        raise AssertionError(f"unexpected GitHub call {method} {url}")

    monkeypatch.setattr(data_sync.requests, "request", fake_request)
    return calls, responses


@pytest.mark.parametrize("identity", [None, "viewer@example.com"])
def test_non_owner_is_refused_on_aws_even_with_disable_auth(identity, github):
    calls, _ = github
    client = _client(identity)
    assert client.get("/support/data-sync").status_code == 403
    assert client.post("/support/data-sync/pull").status_code == 403
    assert calls == []


def test_demo_session_is_refused_even_locally(monkeypatch, github):
    monkeypatch.setattr(data_sync.config, "app_env", "local")
    monkeypatch.setattr(data_sync.auth, "is_demo_request", lambda: True)
    assert _client(OWNER).post("/support/data-sync/push").status_code == 403


def test_local_dev_without_sign_in_is_allowed(monkeypatch, github):
    _, responses = github
    monkeypatch.setattr(data_sync.config, "app_env", "local")
    responses[("GET", "/runs")] = _runs()
    assert _client(None).get("/support/data-sync").status_code == 200


def test_status_reports_the_latest_pull_and_push_runs(github):
    _, responses = github
    responses[("GET", "data-pull.yml/runs")] = _runs("completed", "success")
    responses[("GET", "data-push.yml/runs")] = _response(200, {"workflow_runs": []})

    body = _client("Owner@Example.com").get("/support/data-sync").json()

    assert body["configured"] is True
    assert body["runs"]["pull"]["conclusion"] == "success"
    assert body["runs"]["pull"]["actor"] == "leonarduk"
    assert body["runs"]["push"] is None
    assert body["pulls_url"] == "https://github.com/leonarduk/allotmint-data/pulls"


def test_status_when_not_configured(monkeypatch, github):
    calls, _ = github
    monkeypatch.delenv("DATA_SYNC_GITHUB_TOKEN")
    monkeypatch.delenv("DATA_SYNC_TOKEN_PARAMETER", raising=False)
    assert _client(OWNER).get("/support/data-sync").json() == {
        "configured": False,
        "repo": "leonarduk/allotmint-data",
        "runs": {},
    }
    assert _client(OWNER).post("/support/data-sync/pull").status_code == 503
    assert calls == []


@pytest.mark.parametrize("direction, workflow", [("pull", "data-pull.yml"), ("push", "data-push.yml")])
def test_dispatches_the_workflow_on_main(direction, workflow, github):
    calls, responses = github
    responses[("GET", "/runs")] = _runs()
    responses[("POST", "/dispatches")] = _response(204)

    resp = _client(OWNER).post(f"/support/data-sync/{direction}")

    assert resp.status_code == 202
    assert resp.json() == {"dispatched": direction, "workflow": workflow, "repo": "leonarduk/allotmint-data"}
    method, url, kwargs = calls[-1]
    assert method == "POST"
    assert url == f"https://api.github.com/repos/leonarduk/allotmint-data/actions/workflows/{workflow}/dispatches"
    assert kwargs["json"] == {"ref": "main", "inputs": {"requested_by": OWNER}}
    assert kwargs["headers"]["Authorization"] == "Bearer gh-token"


def test_refuses_while_a_sync_is_running(github):
    calls, responses = github
    responses[("GET", "/runs")] = _runs("in_progress", None)

    resp = _client(OWNER).post("/support/data-sync/pull")

    assert resp.status_code == 409
    assert not any(method == "POST" for method, _, _ in calls)


def test_unknown_direction_is_rejected(github):
    assert _client(OWNER).post("/support/data-sync/sideways").status_code == 422


def test_rejected_token_is_reported_and_not_cached(monkeypatch, github):
    _, responses = github
    monkeypatch.delenv("DATA_SYNC_GITHUB_TOKEN")
    monkeypatch.setenv("DATA_SYNC_TOKEN_PARAMETER", "/allotmint/data-sync/github-token")
    ssm = MagicMock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": "stale-token"}}
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: ssm)
    responses[("GET", "/runs")] = _response(401)

    resp = _client(OWNER).post("/support/data-sync/pull")

    assert resp.status_code == 424
    assert "expired" in resp.json()["detail"]
    # A rotated token in SSM is picked up on the next request.
    assert data_sync._token_cache == {}
