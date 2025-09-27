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
    "path, func_name, expected_args, result_key, payload",
    [
        (
            "/performance/alice/alpha?benchmark=SPY&days=30",
            "alpha_vs_benchmark_breakdown",
            ("alice", "SPY", 30),
            "alpha_vs_benchmark",
            {"alpha_vs_benchmark": 1.23, "daily_breakdown": []},
        ),
        (
            "/performance/alice/tracking-error?benchmark=SPY&days=30",
            "tracking_error_breakdown",
            ("alice", "SPY", 30),
            "tracking_error",
            {
                "tracking_error": 2.34,
                "daily_active_returns": [],
                "standard_deviation": 2.34,
            },
        ),
        (
            "/performance/alice/max-drawdown?days=30",
            "max_drawdown_breakdown",
            ("alice", 30),
            "max_drawdown",
            {
                "max_drawdown": -5.0,
                "drawdown_path": [],
                "peak": None,
                "trough": None,
            },
        ),
        (
            "/performance/alice/twr?days=90",
            "compute_time_weighted_return",
            ("alice", 90),
            "time_weighted_return",
            0.12,
        ),
        (
            "/performance/alice/xirr?days=180",
            "compute_xirr",
            ("alice", 180),
            "xirr",
            0.34,
        ),
    ],
)
def test_owner_metrics_success(path, func_name, expected_args, result_key, payload, monkeypatch):
    def fake(*args):
        assert args == expected_args
        return payload

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"] == "alice"
    if "benchmark" in data:
        assert data["benchmark"] == "SPY"
    value = payload[result_key] if isinstance(payload, dict) else payload
    assert data[result_key] == pytest.approx(value)


@pytest.mark.parametrize(
    "path, func_name, expected_args",
    [
        (
            "/performance/missing/alpha",
            "alpha_vs_benchmark_breakdown",
            ("missing", "VWRL.L", 365),
        ),
        (
            "/performance/missing/tracking-error",
            "tracking_error_breakdown",
            ("missing", "VWRL.L", 365),
        ),
        ("/performance/missing/max-drawdown", "max_drawdown_breakdown", ("missing", 365)),
        ("/performance/missing/twr", "compute_time_weighted_return", ("missing", 365)),
        ("/performance/missing/xirr", "compute_xirr", ("missing", 365)),
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
            "group_alpha_vs_benchmark_breakdown",
            ("demo", "SPY", 30),
            "alpha_vs_benchmark",
            {"alpha_vs_benchmark": 0.5, "daily_breakdown": []},
        ),
        (
            "/performance-group/demo/tracking-error?benchmark=SPY&days=30",
            "group_tracking_error_breakdown",
            ("demo", "SPY", 30),
            "tracking_error",
            {
                "tracking_error": 0.7,
                "daily_active_returns": [],
                "standard_deviation": 0.7,
            },
        ),
        (
            "/performance-group/demo/max-drawdown?days=30",
            "group_max_drawdown_breakdown",
            ("demo", 30),
            "max_drawdown",
            {
                "max_drawdown": -1.0,
                "drawdown_path": [],
                "peak": None,
                "trough": None,
            },
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
    value = return_value[result_key] if isinstance(return_value, dict) else return_value
    assert data[result_key] == pytest.approx(value)


@pytest.mark.parametrize(
    "path, func_name, expected_args",
    [
        (
            "/performance-group/missing/alpha",
            "group_alpha_vs_benchmark_breakdown",
            ("missing", "VWRL.L", 365),
        ),
        (
            "/performance-group/missing/tracking-error",
            "group_tracking_error_breakdown",
            ("missing", "VWRL.L", 365),
        ),
        (
            "/performance-group/missing/max-drawdown",
            "group_max_drawdown_breakdown",
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


def test_owner_holdings_success(monkeypatch):
    expected_rows = [
        {"ticker": "PFE", "value": 1234.56},
        {"ticker": "TSLA", "value": 789.01},
    ]

    def fake(owner, date):
        assert owner == "alice"
        assert date == "2024-01-31"
        return expected_rows

    monkeypatch.setattr(portfolio_utils, "portfolio_value_breakdown", fake)
    client = _auth_client()
    resp = client.get("/performance/alice/holdings", params={"date": "2024-01-31"})
    assert resp.status_code == 200
    assert resp.json() == {
        "owner": "alice",
        "date": "2024-01-31",
        "holdings": expected_rows,
    }


def test_owner_holdings_bad_request(monkeypatch):
    def fake(owner, date):
        assert owner == "alice"
        assert date == "2024-01-31"
        raise ValueError("Invalid date")

    monkeypatch.setattr(portfolio_utils, "portfolio_value_breakdown", fake)
    client = _auth_client()
    resp = client.get("/performance/alice/holdings", params={"date": "2024-01-31"})
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Invalid date"}


def test_returns_compare_success(monkeypatch):
    def fake_cagr(owner, days):
        assert owner == "alice"
        assert days == 180
        return 0.11

    def fake_cash(owner, days):
        assert owner == "alice"
        assert days == 180
        return 0.03

    monkeypatch.setattr(portfolio_utils, "compute_cagr", fake_cagr)
    monkeypatch.setattr(portfolio_utils, "compute_cash_apy", fake_cash)
    client = _auth_client()
    resp = client.get("/returns/compare", params={"owner": "alice", "days": 180})
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", "cagr": 0.11, "cash_apy": 0.03}


def test_returns_compare_not_found(monkeypatch):
    def fake(owner, days):
        assert owner == "missing"
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_cagr", fake)
    monkeypatch.setattr(portfolio_utils, "compute_cash_apy", fake)
    client = _auth_client()
    resp = client.get("/returns/compare", params={"owner": "missing"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"
