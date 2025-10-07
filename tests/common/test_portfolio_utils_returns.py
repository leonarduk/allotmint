import pandas as pd
import pytest

from backend.common import instrument_api, portfolio_utils


def test_compute_alpha_and_tracking_error(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    portfolio_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)

    def fake_portfolio_value_series(
        name: str, days: int, *, group: bool = False, pricing_date=None, **_
    ) -> pd.Series:
        assert name == "alice"
        assert days == 365
        assert group is False
        return portfolio_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series)

    benchmark_df = pd.DataFrame({"Date": dates, "Close": [100.0, 108.0, 112.0]})

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        assert (ticker, exchange, days) == ("SPY", "L", 365)
        return benchmark_df.copy()

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    alpha = portfolio_utils.compute_alpha_vs_benchmark("alice", "SPY.L", days=365)
    assert alpha == pytest.approx(0.03, rel=1e-4)

    tracking_error = portfolio_utils.compute_tracking_error("alice", "SPY.L", days=365)
    assert tracking_error == pytest.approx(0.13001314, rel=1e-4)


def test_compute_metrics_none_when_series_misaligned(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    portfolio_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)

    def fake_portfolio_value_series(
        name: str, days: int, *, group: bool = False, pricing_date=None, **_
    ) -> pd.Series:
        return portfolio_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series)

    # Simulate a benchmark that lacks the overlapping period with the portfolio values.
    benchmark_dates = pd.date_range("2024-02-01", periods=3, freq="D")
    benchmark_df = pd.DataFrame({"Date": benchmark_dates, "Close": [100.0, 108.0, 112.0]})

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return benchmark_df.copy()

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    assert portfolio_utils.compute_alpha_vs_benchmark("alice", "SPY.L", days=365) is None
    assert portfolio_utils.compute_tracking_error("alice", "SPY.L", days=365) is None


def test_group_metrics_and_max_drawdown(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    shared_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)
    benchmark_df = pd.DataFrame({"Date": dates, "Close": [100.0, 108.0, 112.0]})

    group_calls: list[str] = []

    def fake_group_portfolio(name: str, *, pricing_date=None, **_) -> dict[str, str]:
        group_calls.append(name)
        return {"slug": name}

    monkeypatch.setattr(portfolio_utils.group_portfolio, "build_group_portfolio", fake_group_portfolio)

    def fake_portfolio_value_series(
        name: str, days: int, *, group: bool = False, pricing_date=None, **_
    ) -> pd.Series:
        if group:
            # Mirror the real helper by touching the group portfolio builder.
            portfolio_utils.group_portfolio.build_group_portfolio(name)
            return shared_series
        return shared_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_portfolio_value_series)

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return benchmark_df.copy()

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    alpha = portfolio_utils.compute_group_alpha_vs_benchmark("demo-group", "SPY.L", days=365)
    assert alpha == pytest.approx(0.03, rel=1e-4)

    tracking_error = portfolio_utils.compute_group_tracking_error("demo-group", "SPY.L", days=365)
    assert tracking_error == pytest.approx(0.13001314, rel=1e-4)

    assert group_calls == ["demo-group", "demo-group"]

    drawdown_dates = pd.date_range("2024-02-01", periods=4, freq="D")
    drawdown_series = pd.Series([100.0, 120.0, 90.0, 110.0], index=drawdown_dates.date)

    def fake_drawdown_series(
        name: str, days: int, *, group: bool = False, pricing_date=None, **_
    ) -> pd.Series:
        if group:
            portfolio_utils.group_portfolio.build_group_portfolio(name)
            return drawdown_series
        return drawdown_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", fake_drawdown_series)

    max_drawdown = portfolio_utils.compute_max_drawdown("alice", days=365)
    assert max_drawdown == pytest.approx(-0.25, rel=1e-4)

    group_max_drawdown = portfolio_utils.compute_group_max_drawdown("demo-group", days=365)
    assert group_max_drawdown == pytest.approx(-0.25, rel=1e-4)

    assert group_calls == ["demo-group", "demo-group", "demo-group"]


def test_portfolio_value_series_uses_requested_days(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_days: list[int] = []

    def fake_build_owner_portfolio(name: str, *, pricing_date=None, **_) -> dict:
        assert name == "alice"
        return {
            "accounts": [
                {
                    "holdings": [
                        {
                            "ticker": "ABC",
                            "exchange": "L",
                            "units": 1.0,
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr(
        portfolio_utils.portfolio_mod,
        "build_owner_portfolio",
        fake_build_owner_portfolio,
    )
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: (ticker.split(".")[0], "L"),
    )

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        observed_days.append(days)
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        return pd.DataFrame({"Date": dates, "Close": [100, 101, 102, 103, 104]})

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    series = portfolio_utils._portfolio_value_series("alice", 30)
    assert not series.empty
    assert observed_days == [30]
