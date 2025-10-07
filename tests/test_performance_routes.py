import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import portfolio_utils


@pytest.fixture
def client():
    """Return a TestClient for the API."""
    return TestClient(create_app())


@pytest.mark.parametrize(
    "path, func, key, expected_value, breakdown",
    [
        (
            "/performance/alice/alpha",
            "compute_alpha_vs_benchmark",
            "alpha_vs_benchmark",
            0.1,
            {
                "series": [],
                "portfolio_cumulative_return": 0.2,
                "benchmark_cumulative_return": 0.1,
            },
        ),
        (
            "/performance/alice/tracking-error",
            "compute_tracking_error",
            "tracking_error",
            0.2,
            {"active_returns": [], "daily_active_standard_deviation": 0.05},
        ),
        (
            "/performance/alice/max-drawdown",
            "compute_max_drawdown",
            "max_drawdown",
            -0.3,
            {"series": [], "peak": None, "trough": None},
        ),
    ],
)
def test_owner_metrics_success(client, monkeypatch, path, func, key, expected_value, breakdown):
    def fake(owner, *args, **kwargs):
        assert owner == "alice"
        assert kwargs == {"include_breakdown": True, "pricing_date": None}
        return expected_value, breakdown

    monkeypatch.setattr(portfolio_utils, func, fake)
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner"] == "alice"
    assert data[key] == expected_value
    for extra_key, extra_val in breakdown.items():
        assert data[extra_key] == extra_val
    if key in {"alpha_vs_benchmark", "tracking_error"}:
        assert data["benchmark"] == "VWRL.L"


@pytest.mark.parametrize(
    "path, func",
    [
        ("/performance/unknown/alpha", "compute_alpha_vs_benchmark"),
        ("/performance/unknown/tracking-error", "compute_tracking_error"),
        ("/performance/unknown/max-drawdown", "compute_max_drawdown"),
    ],
)
def test_owner_metrics_not_found(client, monkeypatch, path, func):
    def fake(*args, **kwargs):
        assert kwargs == {"include_breakdown": True, "pricing_date": None}
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, func, fake)
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


@pytest.mark.parametrize(
    "path, func, key, expected_value, breakdown",
    [
        (
            "/performance-group/test-group/alpha",
            "compute_group_alpha_vs_benchmark",
            "alpha_vs_benchmark",
            0.4,
            {
                "series": [],
                "portfolio_cumulative_return": 0.3,
                "benchmark_cumulative_return": -0.1,
            },
        ),
        (
            "/performance-group/test-group/tracking-error",
            "compute_group_tracking_error",
            "tracking_error",
            0.5,
            {"active_returns": [], "daily_active_standard_deviation": 0.08},
        ),
        (
            "/performance-group/test-group/max-drawdown",
            "compute_group_max_drawdown",
            "max_drawdown",
            -0.6,
            {"series": [], "peak": None, "trough": None},
        ),
    ],
)
def test_group_metrics_success(client, monkeypatch, path, func, key, expected_value, breakdown):
    def fake(slug, *args, **kwargs):
        assert slug == "test-group"
        assert kwargs == {"include_breakdown": True}
        return expected_value, breakdown

    monkeypatch.setattr(portfolio_utils, func, fake)
    resp = client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"] == "test-group"
    assert data[key] == expected_value
    for extra_key, extra_val in breakdown.items():
        assert data[extra_key] == extra_val
    if key in {"alpha_vs_benchmark", "tracking_error"}:
        assert data["benchmark"] == "VWRL.L"


@pytest.mark.parametrize(
    "path, func",
    [
        ("/performance-group/missing/alpha", "compute_group_alpha_vs_benchmark"),
        ("/performance-group/missing/tracking-error", "compute_group_tracking_error"),
        ("/performance-group/missing/max-drawdown", "compute_group_max_drawdown"),
    ],
)
def test_group_metrics_not_found(client, monkeypatch, path, func):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, func, fake)
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_performance_summary_success(client, monkeypatch):
    result = {
        "history": [{"date": "2024-01-01", "cumulative_return": 0.07}],
        "max_drawdown": -0.4,
        "reporting_date": "2024-01-01",
        "previous_date": "2023-12-29",
    }

    def fake(owner, *args, **kwargs):
        assert owner == "alice"
        return result

    monkeypatch.setattr(
        portfolio_utils, "compute_owner_performance", fake
    )
    resp = client.get("/performance/alice")
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", **result}


def test_performance_summary_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(
        portfolio_utils, "compute_owner_performance", fake
    )
    resp = client.get("/performance/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


def test_returns_compare_success(client, monkeypatch):
    def fake_cagr(owner, days):
        assert owner == "alice"
        assert days == 365
        return 0.05

    def fake_cash(owner, days):
        assert owner == "alice"
        assert days == 365
        return 0.02

    monkeypatch.setattr(portfolio_utils, "compute_cagr", fake_cagr)
    monkeypatch.setattr(portfolio_utils, "compute_cash_apy", fake_cash)
    resp = client.get("/returns/compare", params={"owner": "alice", "days": 365})
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", "cagr": 0.05, "cash_apy": 0.02}


def test_returns_compare_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_cagr", fake)
    monkeypatch.setattr(portfolio_utils, "compute_cash_apy", fake)
    resp = client.get("/returns/compare", params={"owner": "bob"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Owner not found"


def test_group_alpha_handles_near_zero_benchmark(client, monkeypatch):
    dates = pd.to_datetime(["2024-01-01", "2024-01-02"]).date
    port_series = pd.Series([100.0, 101.0], index=dates)

    def fake_portfolio_value_series(name, days, *, group=False, pricing_date=None):
        assert name == "test-group"
        assert group is True
        assert days == 365
        return port_series

    def fake_load_meta_timeseries(ticker, exchange, days):
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "Close": [0.0, 1e-6],
            }
        )

    monkeypatch.setattr(
        portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series
    )
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    resp = client.get("/performance-group/test-group/alpha")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "group": "test-group",
        "benchmark": "VWRL.L",
        "alpha_vs_benchmark": None,
        "portfolio_cumulative_return": None,
        "benchmark_cumulative_return": None,
        "series": [],
    }
