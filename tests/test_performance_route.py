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
    "path, func_name, expected_args, expected_kwargs, result_key, return_value, extra_keys",
    [
        (
            "/performance/alice/alpha?benchmark=SPY&days=30",
            "compute_alpha_vs_benchmark",
            ("alice", "SPY", 30),
            {"include_breakdown": True},
            "alpha_vs_benchmark",
            (
                1.23,
                {
                    "series": [
                        {
                            "date": "2024-01-01",
                            "portfolio_cumulative_return": 0.1,
                            "benchmark_cumulative_return": 0.05,
                            "excess_cumulative_return": 0.05,
                        }
                    ],
                    "portfolio_cumulative_return": 0.1,
                    "benchmark_cumulative_return": 0.05,
                },
            ),
            [
                "series",
                "portfolio_cumulative_return",
                "benchmark_cumulative_return",
            ],
        ),
        (
            "/performance/alice/tracking-error?benchmark=SPY&days=30",
            "compute_tracking_error",
            ("alice", "SPY", 30),
            {"include_breakdown": True},
            "tracking_error",
            (
                2.34,
                {
                    "active_returns": [
                        {
                            "date": "2024-01-02",
                            "portfolio_return": 0.01,
                            "benchmark_return": 0.005,
                            "active_return": 0.005,
                        }
                    ],
                    "daily_active_standard_deviation": 0.15,
                },
            ),
            ["active_returns", "daily_active_standard_deviation"],
        ),
        (
            "/performance/alice/max-drawdown?days=30",
            "compute_max_drawdown",
            ("alice", 30),
            {"include_breakdown": True},
            "max_drawdown",
            (
                -5.0,
                {
                    "series": [
                        {
                            "date": "2024-01-01",
                            "portfolio_value": 100.0,
                            "running_max": 100.0,
                            "drawdown": 0.0,
                        }
                    ],
                    "peak": {"date": "2024-01-01", "value": 100.0},
                    "trough": {
                        "date": "2024-01-01",
                        "value": 95.0,
                        "drawdown": -0.05,
                    },
                },
            ),
            ["series", "peak", "trough"],
        ),
        (
            "/performance/alice/twr?days=90",
            "compute_time_weighted_return",
            ("alice", 90),
            {},
            "time_weighted_return",
            0.12,
            [],
        ),
        (
            "/performance/alice/xirr?days=180",
            "compute_xirr",
            ("alice", 180),
            {},
            "xirr",
            0.34,
            [],
        ),
    ],
)
def test_owner_metrics_success(
    path,
    func_name,
    expected_args,
    expected_kwargs,
    result_key,
    return_value,
    extra_keys,
    monkeypatch,
):
    def fake(*args, **kwargs):
        assert args == expected_args
        assert kwargs == expected_kwargs
        return return_value

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"] == "alice"
    if "benchmark" in data:
        assert data["benchmark"] == "SPY"
    if isinstance(return_value, tuple):
        expected_val = return_value[0]
        assert data[result_key] == pytest.approx(expected_val)
        breakdown = return_value[1]
        for key in extra_keys:
            assert data[key] == breakdown.get(key)
    else:
        assert data[result_key] == pytest.approx(return_value)


@pytest.mark.parametrize(
    "path, func_name, expected_args, expected_kwargs",
    [
        (
            "/performance/missing/alpha",
            "compute_alpha_vs_benchmark",
            ("missing", "VWRL.L", 365),
            {"include_breakdown": True},
        ),
        (
            "/performance/missing/tracking-error",
            "compute_tracking_error",
            ("missing", "VWRL.L", 365),
            {"include_breakdown": True},
        ),
        (
            "/performance/missing/max-drawdown",
            "compute_max_drawdown",
            ("missing", 365),
            {"include_breakdown": True},
        ),
        (
            "/performance/missing/twr",
            "compute_time_weighted_return",
            ("missing", 365),
            {},
        ),
        (
            "/performance/missing/xirr",
            "compute_xirr",
            ("missing", 365),
            {},
        ),
    ],
)
def test_owner_metrics_not_found(path, func_name, expected_args, expected_kwargs, monkeypatch):
    def fake(*args, **kwargs):
        assert args == expected_args
        assert kwargs == expected_kwargs
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


@pytest.mark.parametrize(
    "path, func_name, expected_args, expected_kwargs, result_key, return_value, extra_keys",
    [
        (
            "/performance-group/demo/alpha?benchmark=SPY&days=30",
            "compute_group_alpha_vs_benchmark",
            ("demo", "SPY", 30),
            {"include_breakdown": True},
            "alpha_vs_benchmark",
            (
                0.5,
                {
                    "series": [],
                    "portfolio_cumulative_return": 0.2,
                    "benchmark_cumulative_return": -0.3,
                },
            ),
            [
                "series",
                "portfolio_cumulative_return",
                "benchmark_cumulative_return",
            ],
        ),
        (
            "/performance-group/demo/tracking-error?benchmark=SPY&days=30",
            "compute_group_tracking_error",
            ("demo", "SPY", 30),
            {"include_breakdown": True},
            "tracking_error",
            (
                0.7,
                {
                    "active_returns": [],
                    "daily_active_standard_deviation": 0.2,
                },
            ),
            ["active_returns", "daily_active_standard_deviation"],
        ),
        (
            "/performance-group/demo/max-drawdown?days=30",
            "compute_group_max_drawdown",
            ("demo", 30),
            {"include_breakdown": True},
            "max_drawdown",
            (
                -1.0,
                {
                    "series": [],
                    "peak": None,
                    "trough": None,
                },
            ),
            ["series", "peak", "trough"],
        ),
    ],
)
def test_group_metrics_success(
    path,
    func_name,
    expected_args,
    expected_kwargs,
    result_key,
    return_value,
    extra_keys,
    monkeypatch,
):
    def fake(*args, **kwargs):
        assert args == expected_args
        assert kwargs == expected_kwargs
        return return_value

    monkeypatch.setattr(portfolio_utils, func_name, fake)
    client = _auth_client()
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"] == "demo"
    if "benchmark" in data:
        assert data["benchmark"] == "SPY"
    expected_val = return_value[0]
    assert data[result_key] == pytest.approx(expected_val)
    breakdown = return_value[1]
    for key in extra_keys:
        assert data[key] == breakdown.get(key)


@pytest.mark.parametrize(
    "path, func_name, expected_args, expected_kwargs",
    [
        (
            "/performance-group/missing/alpha",
            "compute_group_alpha_vs_benchmark",
            ("missing", "VWRL.L", 365),
            {"include_breakdown": True},
        ),
        (
            "/performance-group/missing/tracking-error",
            "compute_group_tracking_error",
            ("missing", "VWRL.L", 365),
            {"include_breakdown": True},
        ),
        (
            "/performance-group/missing/max-drawdown",
            "compute_group_max_drawdown",
            ("missing", 365),
            {"include_breakdown": True},
        ),
    ],
)
def test_group_metrics_not_found(path, func_name, expected_args, expected_kwargs, monkeypatch):
    def fake(*args, **kwargs):
        assert args == expected_args
        assert kwargs == expected_kwargs
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
