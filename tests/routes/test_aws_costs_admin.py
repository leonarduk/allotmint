from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import aws_costs_admin
from backend.routes.aws_costs_admin import router


@pytest.fixture(autouse=True)
def _clear_cache():
    aws_costs_admin._cache.clear()
    yield
    aws_costs_admin._cache.clear()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_response(*groups):
    return {
        "ResultsByTime": [
            {
                "Groups": [
                    {
                        "Keys": [service],
                        "Metrics": {"UnblendedCost": {"Amount": str(amount), "Unit": "USD"}},
                    }
                    for service, amount in groups
                ]
            }
        ]
    }


def test_returns_services_sorted_with_total(client, monkeypatch):
    fake_client = MagicMock()
    fake_client.get_cost_and_usage.return_value = _fake_response(
        ("Amazon Simple Storage Service", "1.50"),
        ("AWS Lambda", "3.25"),
    )
    monkeypatch.setattr(aws_costs_admin.boto3, "client", lambda *a, **k: fake_client)

    resp = client.get("/admin/aws-costs", params={"start": "2026-09-01", "end": "2026-09-27"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == {"amount": 4.75, "unit": "USD"}
    assert body["services"] == [
        {"service": "AWS Lambda", "amount": 3.25, "unit": "USD"},
        {"service": "Amazon Simple Storage Service", "amount": 1.5, "unit": "USD"},
    ]


def test_second_call_within_ttl_does_not_hit_cost_explorer_again(client, monkeypatch):
    fake_client = MagicMock()
    fake_client.get_cost_and_usage.return_value = _fake_response(("AWS Lambda", "1.00"))
    monkeypatch.setattr(aws_costs_admin.boto3, "client", lambda *a, **k: fake_client)

    params = {"start": "2026-09-01", "end": "2026-09-27"}
    first = client.get("/admin/aws-costs", params=params)
    second = client.get("/admin/aws-costs", params=params)

    assert first.status_code == second.status_code == 200
    assert fake_client.get_cost_and_usage.call_count == 1


def test_end_before_start_returns_400(client):
    resp = client.get("/admin/aws-costs", params={"start": "2026-09-27", "end": "2026-09-01"})
    assert resp.status_code == 400


def test_cost_explorer_error_returns_502(client, monkeypatch):
    fake_client = MagicMock()
    fake_client.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "DataUnavailableException", "Message": "not enabled"}},
        "GetCostAndUsage",
    )
    monkeypatch.setattr(aws_costs_admin.boto3, "client", lambda *a, **k: fake_client)

    resp = client.get("/admin/aws-costs", params={"start": "2026-09-01", "end": "2026-09-27"})
    assert resp.status_code == 502


def test_unparseable_dates_return_400(client):
    resp = client.get("/admin/aws-costs", params={"start": "not-a-date", "end": "2026-09-27"})
    assert resp.status_code == 400


def test_non_owner_identity_forbidden_when_auth_enabled(client, monkeypatch):
    monkeypatch.setattr(aws_costs_admin.config, "disable_auth", False)
    monkeypatch.setattr(aws_costs_admin.config, "allowed_emails", ["owner@example.com"])
    client.app.dependency_overrides[aws_costs_admin.get_active_user] = lambda: "viewer@example.com"
    try:
        resp = client.get("/admin/aws-costs", params={"start": "2026-09-01", "end": "2026-09-27"})
    finally:
        client.app.dependency_overrides.pop(aws_costs_admin.get_active_user, None)
    assert resp.status_code == 403


def test_owner_identity_allowed_when_auth_enabled(client, monkeypatch):
    fake_client = MagicMock()
    fake_client.get_cost_and_usage.return_value = _fake_response(("AWS Lambda", "1.00"))
    monkeypatch.setattr(aws_costs_admin.boto3, "client", lambda *a, **k: fake_client)
    monkeypatch.setattr(aws_costs_admin.config, "disable_auth", False)
    monkeypatch.setattr(aws_costs_admin.config, "allowed_emails", ["owner@example.com"])
    client.app.dependency_overrides[aws_costs_admin.get_active_user] = lambda: "Owner@Example.com"
    try:
        resp = client.get("/admin/aws-costs", params={"start": "2026-09-01", "end": "2026-09-27"})
    finally:
        client.app.dependency_overrides.pop(aws_costs_admin.get_active_user, None)
    assert resp.status_code == 200


def test_no_identity_forbidden_when_auth_enabled(client, monkeypatch):
    monkeypatch.setattr(aws_costs_admin.config, "disable_auth", False)
    monkeypatch.setattr(aws_costs_admin.config, "allowed_emails", ["owner@example.com"])
    client.app.dependency_overrides[aws_costs_admin.get_active_user] = lambda: None
    try:
        resp = client.get("/admin/aws-costs", params={"start": "2026-09-01", "end": "2026-09-27"})
    finally:
        client.app.dependency_overrides.pop(aws_costs_admin.get_active_user, None)
    assert resp.status_code == 403
