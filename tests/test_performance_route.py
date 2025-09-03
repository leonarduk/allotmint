import pytest
from fastapi.testclient import TestClient

from backend.common import portfolio_utils
from backend.local_api.main import app


def _auth_client():
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.mark.parametrize(
    "path, func_name, expected_args, result_key, return_value",
    [
        (
            "/performance/alice/alpha?benchmark=SPY&days=30",
            "compute_alpha_vs_benchmark",
            ("alice", "SPY", 30),
            "alpha_vs_benchmark",
            1.23,
        ),
        (
            "/performance/alice/tracking-error?benchmark=SPY&days=30",
            "compute_tracking_error",
            ("alice", "SPY", 30),
            "tracking_error",
            2.34,
        ),
        (
            "/performance/alice/max-drawdown?days=30",
            "compute_max_drawdown",
            ("alice", 30),
            "max_drawdown",
            -5.0,
        ),
    ],
)
def test_owner_metrics_success(path, func_name, expected_args, result_key, return_value, monkeypatch):
    def fake(*args):
        assert args == expected_args
        return return_value

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"] == "alice"
    if "benchmark" in data:
        assert data["benchmark"] == "SPY"
    assert data[result_key] == pytest.approx(return_value)


@pytest.mark.parametrize(
    "path, func_name, expected_args",
    [
        ("/performance/missing/alpha", "compute_alpha_vs_benchmark", ("missing", "VWRL.L", 365)),
        (
            "/performance/missing/tracking-error",
            "compute_tracking_error",
            ("missing", "VWRL.L", 365),
        ),
        ("/performance/missing/max-drawdown", "compute_max_drawdown", ("missing", 365)),
    ],
)
def test_owner_metrics_not_found(path, func_name, expected_args, monkeypatch):
    def fake(*args):
        assert args == expected_args
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


@pytest.mark.parametrize(
    "path, func_name, expected_args, result_key, return_value",
    [
        (
            "/performance-group/demo/alpha?benchmark=SPY&days=30",
            "compute_group_alpha_vs_benchmark",
            ("demo", "SPY", 30),
            "alpha_vs_benchmark",
            0.5,
        ),
        (
            "/performance-group/demo/tracking-error?benchmark=SPY&days=30",
            "compute_group_tracking_error",
            ("demo", "SPY", 30),
            "tracking_error",
            0.7,
        ),
        (
            "/performance-group/demo/max-drawdown?days=30",
            "compute_group_max_drawdown",
            ("demo", 30),
            "max_drawdown",
            -1.0,
        ),
    ],
)
def test_group_metrics_success(path, func_name, expected_args, result_key, return_value, monkeypatch):
    def fake(*args):
        assert args == expected_args
        return return_value

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"] == "demo"
    if "benchmark" in data:
        assert data["benchmark"] == "SPY"
    assert data[result_key] == pytest.approx(return_value)


@pytest.mark.parametrize(
    "path, func_name, expected_args",
    [
        (
            "/performance-group/missing/alpha",
            "compute_group_alpha_vs_benchmark",
            ("missing", "VWRL.L", 365),
        ),
        (
            "/performance-group/missing/tracking-error",
            "compute_group_tracking_error",
            ("missing", "VWRL.L", 365),
        ),
        (
            "/performance-group/missing/max-drawdown",
            "compute_group_max_drawdown",
            ("missing", 365),
        ),
    ],
)
def test_group_metrics_not_found(path, func_name, expected_args, monkeypatch):
    def fake(*args):
        assert args == expected_args
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_owner_performance_success(monkeypatch):
    def fake(owner, *, days, include_cash):
        assert owner == "alice"
        assert days == 30
        assert include_cash is False
        return {"total_return": 9.9}

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    client = _auth_client()
    resp = client.get("/performance/alice?days=30&exclude_cash=true")
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", "total_return": 9.9}


def test_owner_performance_not_found(monkeypatch):
    def fake(owner, *, days, include_cash):
        assert owner == "missing"
        assert days == 365
        assert include_cash is True
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    client = _auth_client()
    resp = client.get("/performance/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"
