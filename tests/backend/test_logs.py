from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import config
from backend.routes.logs import router


def create_app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_logs_endpoint_returns_content(tmp_path, monkeypatch):
    log_file = tmp_path / "logs" / "backend.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("line1\nline2\n", encoding="utf-8")
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs")
    assert resp.status_code == 200
    assert "line2" in resp.text


def test_logs_endpoint_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Log file not found"


def test_logs_endpoint_respects_lines_parameter(tmp_path, monkeypatch):
    log_file = tmp_path / "logs" / "backend.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        """line1
line2
line3
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "repo_root", tmp_path)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs", params={"lines": 2})
    assert resp.status_code == 200
    assert resp.text.strip().splitlines() == ["line2", "line3"]


def test_logs_endpoint_aws_missing_log_group_returns_404(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.delenv("BACKEND_LOG_GROUP_NAME", raising=False)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/logs")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "CloudWatch log group not configured"


def test_logs_endpoint_aws_returns_recent_events_in_order(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("BACKEND_LOG_GROUP_NAME", "test-log-group")
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {
            "events": [
                {"timestamp": 300, "message": "line3"},
                {"timestamp": 100, "message": "line1"},
                {"timestamp": 200, "message": "line2"},
            ]
        }
    ]

    with patch("boto3.client", return_value=mock_client):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/logs", params={"lines": 2})

    assert resp.status_code == 200
    assert resp.text.strip().splitlines() == ["line2", "line3"]
    mock_client.get_paginator.assert_called_once_with("filter_log_events")
    _, paginate_kwargs = mock_client.get_paginator.return_value.paginate.call_args
    assert paginate_kwargs["logGroupName"] == "test-log-group"


def test_logs_endpoint_aws_no_events_returns_404(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("BACKEND_LOG_GROUP_NAME", "test-log-group")
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [{"events": []}]

    with patch("boto3.client", return_value=mock_client):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/logs")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "No log events found"


def test_logs_endpoint_aws_client_error_returns_502(monkeypatch):
    from botocore.exceptions import ClientError

    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setenv("BACKEND_LOG_GROUP_NAME", "test-log-group")
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "FilterLogEvents",
    )

    with patch("boto3.client", return_value=mock_client):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/logs")

    assert resp.status_code == 502
