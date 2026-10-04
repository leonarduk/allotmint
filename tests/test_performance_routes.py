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


def test_group_performance_summary_success(client, monkeypatch):
    result = {
        "history": [{"date": "2024-01-01", "cumulative_return": 0.07}],
        "max_drawdown": -0.4,
        "reporting_date": "2024-01-01",
        "previous_date": "2023-12-29",
    }

    def fake(slug, *args, **kwargs):
        assert slug == "test-group"
        assert kwargs == {
            "days": 365,
            "include_cash": True,
            "pricing_date": None,
            "group": True,
        }
        return result

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    resp = client.get("/performance-group/test-group")
    assert resp.status_code == 200
    assert resp.json() == {"group": "test-group", **result}


def test_group_performance_summary_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    resp = client.get("/performance-group/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_group_performance_summary_unknown_slug_raises_value_error(client, monkeypatch):
    def fake(*args, **kwargs):
        raise ValueError("Unknown group slug: 'missing'")

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    resp = client.get("/performance-group/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_group_twr_success(client, monkeypatch):
    def fake(slug, days, *, pricing_date=None, group=False, include_missing_members=False):
        assert slug == "test-group"
        assert days == 365
        assert group is True
        assert include_missing_members is True
        return 0.042, []

    monkeypatch.setattr(portfolio_utils, "compute_time_weighted_return", fake)
    resp = client.get("/performance-group/test-group/twr")
    assert resp.status_code == 200
    assert resp.json() == {
        "group": "test-group",
        "time_weighted_return": 0.042,
        "partial": False,
        "missing_members": [],
    }


def test_group_twr_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise ValueError("Unknown group slug: 'missing'")

    monkeypatch.setattr(portfolio_utils, "compute_time_weighted_return", fake)
    resp = client.get("/performance-group/missing/twr")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_group_twr_reports_partial_when_a_member_ledger_is_missing(client, monkeypatch):
    """#7228 review MUST FIX 1: a missing member's transaction ledger must be
    surfaced to the caller, not silently dropped from the figure.
    """

    def fake(slug, days, *, pricing_date=None, group=False, include_missing_members=False):
        assert include_missing_members is True
        return 0.042, ["ghost"]

    monkeypatch.setattr(portfolio_utils, "compute_time_weighted_return", fake)
    resp = client.get("/performance-group/test-group/twr")
    assert resp.status_code == 200
    body = resp.json()
    assert body["partial"] is True
    assert body["missing_members"] == ["ghost"]


def test_group_xirr_success(client, monkeypatch):
    def fake(slug, days, *, pricing_date=None, group=False, include_missing_members=False):
        assert slug == "test-group"
        assert days == 365
        assert group is True
        assert include_missing_members is True
        return 0.055, []

    monkeypatch.setattr(portfolio_utils, "compute_xirr", fake)
    resp = client.get("/performance-group/test-group/xirr")
    assert resp.status_code == 200
    assert resp.json() == {
        "group": "test-group",
        "xirr": 0.055,
        "partial": False,
        "missing_members": [],
    }


def test_group_xirr_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_xirr", fake)
    resp = client.get("/performance-group/missing/xirr")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Group not found"


def test_group_xirr_reports_partial_when_a_member_ledger_is_missing(client, monkeypatch):
    """#7228 review MUST FIX 1: same partial-data signal as TWR."""

    def fake(slug, days, *, pricing_date=None, group=False, include_missing_members=False):
        assert include_missing_members is True
        return 0.11, ["ghost"]

    monkeypatch.setattr(portfolio_utils, "compute_xirr", fake)
    resp = client.get("/performance-group/test-group/xirr")
    assert resp.status_code == 200
    body = resp.json()
    assert body["partial"] is True
    assert body["missing_members"] == ["ghost"]


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

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
    resp = client.get("/performance/alice")
    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", **result}


def test_performance_summary_not_found(client, monkeypatch):
    def fake(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_utils, "compute_owner_performance", fake)
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

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series)
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


# ---------------------------------------------------------------------------
# Unit contract (#8570): every headline metric the Performance page reads is
# a FRACTION (0.015 = 1.5%), on the owner AND the group routes. The frontend
# formats these as ``value * 100`` with no "|x| > 1 means percent" guessing,
# so a route that started returning percent would silently render 100x too
# large. These tests run the real calculations end to end through the routes
# (only the price/ledger inputs are faked) and pin the unit.
# ---------------------------------------------------------------------------

# Exactly one year apart (2024 is a leap year: Jan 1 -> Dec 31 is 365 days),
# so XIRR over the window equals the simple return.
_UNIT_DATES = pd.to_datetime(["2024-01-01", "2024-05-01", "2024-09-01", "2024-12-31"]).date
_UNIT_VALUES = [100.0, 101.0, 99.99, 101.5]


@pytest.fixture
def unit_inputs(monkeypatch):
    series = pd.Series(_UNIT_VALUES, index=_UNIT_DATES)

    def fake_portfolio_value_series(name, days, *, group=False, pricing_date=None, **_):
        return series

    def fake_load_meta_timeseries(ticker, exchange, days):
        # Flat benchmark: alpha == portfolio return, tracking error == the
        # annualised std-dev of the portfolio's own period returns.
        return pd.DataFrame({"Date": pd.to_datetime(list(_UNIT_DATES)), "Close": [100.0] * 4})

    # A single 100.00 deposit on day one, so XIRR has a cash flow to solve.
    txs = [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 10000}]

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series)
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)
    monkeypatch.setattr(portfolio_utils, "load_transactions", lambda owner: list(txs))
    monkeypatch.setattr(portfolio_utils, "_group_transactions", lambda slug: (list(txs), []))
    return series


def _expected_unit_metrics(series: pd.Series) -> dict[str, float]:
    rets = series.pct_change().dropna()
    return {
        "alpha_vs_benchmark": 0.015,  # 101.5 / 100 - 1, benchmark flat
        "tracking_error": float(rets.std() * (252**0.5)),
        "max_drawdown": 99.99 / 101.0 - 1,  # about -0.01
        "time_weighted_return": 0.015,
        "xirr": 0.015,
    }


@pytest.mark.parametrize("prefix", ["/performance/alice", "/performance-group/all"])
@pytest.mark.parametrize(
    "suffix, key",
    [
        ("alpha", "alpha_vs_benchmark"),
        ("tracking-error", "tracking_error"),
        ("max-drawdown", "max_drawdown"),
        ("twr", "time_weighted_return"),
        ("xirr", "xirr"),
    ],
)
def test_performance_metrics_are_returned_as_fractions(client, unit_inputs, prefix, suffix, key):
    resp = client.get(f"{prefix}/{suffix}")
    assert resp.status_code == 200, resp.text
    value = resp.json()[key]
    expected = _expected_unit_metrics(unit_inputs)[key]
    # A percent-unit response would be 100x this (e.g. 1.5 instead of 0.015).
    assert value == pytest.approx(expected, rel=1e-4, abs=1e-6)
    assert abs(value) < 1
