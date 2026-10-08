import pandas as pd
import pytest

from backend.common import instrument_api, portfolio_utils


def _as_return_series(fake):
    """Adapt a ``_portfolio_value_series`` fake to ``_portfolio_return_series`` (#9571)."""
    return lambda *a, **k: (fake(*a, **k), {"portfolio_return_basis": "price", "portfolio_price_basis_share": 1.0})


def test_compute_alpha_and_tracking_error(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    portfolio_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)

    def fake_portfolio_value_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_) -> pd.Series:
        assert name == "alice"
        assert days == 365
        assert group is False
        return portfolio_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_return_series", _as_return_series(fake_portfolio_value_series))

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

    def fake_portfolio_value_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_) -> pd.Series:
        return portfolio_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_return_series", _as_return_series(fake_portfolio_value_series))

    # Simulate a benchmark that lacks the overlapping period with the portfolio values.
    benchmark_dates = pd.date_range("2024-02-01", periods=3, freq="D")
    benchmark_df = pd.DataFrame({"Date": benchmark_dates, "Close": [100.0, 108.0, 112.0]})

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return benchmark_df.copy()

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    assert portfolio_utils.compute_alpha_vs_benchmark("alice", "SPY.L", days=365) is None
    assert portfolio_utils.compute_tracking_error("alice", "SPY.L", days=365) is None


def test_compute_metrics_none_when_benchmark_data_entirely_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A benchmark with no cached/fetchable data must degrade gracefully.

    Regression test for #5286: the leading theory for a reported 404 on
    `/performance/{owner}/tracking-error` was a missing benchmark data file.
    load_meta_timeseries returning a genuinely empty frame (rather than
    raising) must produce ``None`` results, not an exception that a route
    handler could mistranslate into a 404 "Owner not found".
    """

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    portfolio_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)

    def fake_portfolio_value_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_) -> pd.Series:
        return portfolio_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_return_series", _as_return_series(fake_portfolio_value_series))

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    assert portfolio_utils.compute_alpha_vs_benchmark("alice", "MISSING.L", days=365) is None
    assert portfolio_utils.compute_tracking_error("alice", "MISSING.L", days=365) is None


def test_group_metrics_and_max_drawdown(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    shared_series = pd.Series([100.0, 110.0, 115.0], index=dates.date)
    benchmark_df = pd.DataFrame({"Date": dates, "Close": [100.0, 108.0, 112.0]})

    group_calls: list[str] = []

    def fake_group_portfolio(name: str, *, pricing_date=None, **_) -> dict[str, str]:
        group_calls.append(name)
        return {"slug": name}

    monkeypatch.setattr(portfolio_utils.group_portfolio, "build_group_portfolio", fake_group_portfolio)

    def fake_portfolio_value_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_) -> pd.Series:
        if group:
            # Mirror the real helper by touching the group portfolio builder.
            portfolio_utils.group_portfolio.build_group_portfolio(name)
            return shared_series
        return shared_series

    monkeypatch.setattr(portfolio_utils, "_portfolio_return_series", _as_return_series(fake_portfolio_value_series))

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

    def fake_drawdown_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_) -> pd.Series:
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


def test_fx_failed_holding_appears_in_unpriced_and_seeds_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A holding that prices but fails FX conversion must not be silently dropped.

    Regression test: previously such a holding was skipped entirely, so it
    contributed to neither ``portfolio_price_basis_share`` nor
    ``portfolio_unpriced_holdings`` and did not push ``portfolio_return_basis``
    toward its known basis. It must now appear under
    ``portfolio_unpriced_holdings`` and seed ``bases`` in
    ``_portfolio_return_basis``.
    """
    from datetime import date

    dates = pd.date_range("2024-01-01", periods=3, freq="D")

    # Two holdings: one price-only that prices and converts fine, one
    # total-return holding that prices but has no FX rate on any date.
    holdings = [("AAA", "L", 1.0), ("BBB", "L", 1.0)]

    def fake_window_closes(ticker, exchange, effective_days, window, *, total_return):
        closes = pd.Series([100.0, 101.0, 102.0], index=[d.date() for d in dates])
        if ticker == "AAA":
            return closes, portfolio_utils.PRICE_RETURN_BASIS
        # BBB is a total-return holding.
        return closes, "total"

    monkeypatch.setattr(portfolio_utils, "_window_closes", fake_window_closes)

    def fake_closes_in_gbp(closes, ticker, exchange):
        if ticker == "AAA":
            return closes, "GBP", pd.Index([])
        # BBB prices but has no usable FX rate on any date.
        return pd.Series(dtype=float), "USD", pd.Index(closes.index)

    monkeypatch.setattr(portfolio_utils, "_closes_in_gbp", fake_closes_in_gbp)

    def fake_stored_return_basis(ticker, exchange, *, first_close):
        return "total"

    monkeypatch.setattr(portfolio_utils, "stored_return_basis", fake_stored_return_basis)

    window = (date(2024, 1, 1), date(2024, 1, 3))
    per_holding, _unconverted, unpriced = portfolio_utils._gbp_holding_values(
        holdings, 365, window, total_return=True
    )

    # BBB must be surfaced as unpriced with its intended (total) basis.
    assert any(entry["ticker"] == "BBB.L" for entry in unpriced)
    bbb = next(entry for entry in unpriced if entry["ticker"] == "BBB.L")
    assert bbb["return_basis"] == "total"

    # And it must seed ``bases`` in ``_portfolio_return_basis``: paired with a
    # price-only holding the label becomes "mixed", not "price".
    basis_fields = portfolio_utils._portfolio_return_basis(per_holding, unpriced)
    assert basis_fields["portfolio_return_basis"] == portfolio_utils.MIXED_RETURN_BASIS
    assert any(entry["ticker"] == "BBB.L" for entry in basis_fields["portfolio_unpriced_holdings"])


def test_fx_failed_cash_is_not_listed_as_unpriced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cash that fails FX conversion must remain excluded from ``unpriced``."""
    from datetime import date

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    holdings = [("CASH", "USD", 1.0)]

    def fake_window_closes(ticker, exchange, effective_days, window, *, total_return):
        closes = pd.Series([1.0, 1.0, 1.0], index=[d.date() for d in dates])
        return closes, None

    monkeypatch.setattr(portfolio_utils, "_window_closes", fake_window_closes)

    def fake_closes_in_gbp(closes, ticker, exchange):
        return pd.Series(dtype=float), "USD", pd.Index(closes.index)

    monkeypatch.setattr(portfolio_utils, "_closes_in_gbp", fake_closes_in_gbp)

    window = (date(2024, 1, 1), date(2024, 1, 3))
    _per_holding, _unconverted, unpriced = portfolio_utils._gbp_holding_values(
        holdings, 365, window, total_return=False
    )

    assert unpriced == []
