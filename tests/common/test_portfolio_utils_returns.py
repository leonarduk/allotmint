from datetime import date

import pandas as pd
import pytest

from backend.common import instrument_api, portfolio_utils
from backend.timeseries.total_return import MIXED_RETURN_BASIS, PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS


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


def _patch_fx_failure(monkeypatch: pytest.MonkeyPatch, bases: dict[str, str | None], failing: set[str]) -> None:
    """Price each ticker on ``bases[ticker]``; tickers in ``failing`` have no FX rate on any date."""
    index = list(pd.date_range("2024-01-01", periods=3, freq="D").date)

    def fake_window_closes(ticker, exchange, effective_days, window, *, total_return):
        return pd.Series([100.0, 101.0, 102.0], index=index), bases[ticker]

    def fake_closes_in_gbp(closes, ticker, exchange):
        if ticker in failing:
            return pd.Series(dtype=float), "USD", pd.Index(closes.index)
        return closes, "GBP", pd.Index([])

    def fail_stored_return_basis(*_args, **_kwargs):
        raise AssertionError("an FX-failed holding was priced; its basis must come from the priced path")

    monkeypatch.setattr(portfolio_utils, "_window_closes", fake_window_closes)
    monkeypatch.setattr(portfolio_utils, "_closes_in_gbp", fake_closes_in_gbp)
    monkeypatch.setattr(portfolio_utils, "stored_return_basis", fail_stored_return_basis)


_FX_WINDOW = (date(2024, 1, 1), date(2024, 1, 3))


def test_fx_failed_holding_appears_in_unpriced_and_seeds_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A holding that prices but fails FX conversion must not be silently dropped (#10338).

    Previously it was skipped entirely, so it contributed to neither
    ``portfolio_price_basis_share`` nor ``portfolio_unpriced_holdings`` and did
    not push ``portfolio_return_basis`` toward its known basis. It must now be
    listed as unpriced with the basis its closes were priced on, and seed
    ``bases`` in ``_portfolio_return_basis``.
    """
    _patch_fx_failure(monkeypatch, {"AAA": PRICE_RETURN_BASIS, "BBB": TOTAL_RETURN_BASIS}, failing={"BBB"})

    per_holding, unconverted, unpriced = portfolio_utils._gbp_holding_values(
        [("AAA", "L", 1.0), ("BBB", "L", 1.0)], 365, _FX_WINDOW, total_return=True
    )

    assert unpriced == [{"ticker": "BBB.L", "return_basis": TOTAL_RETURN_BASIS}]
    assert [entry["ticker"] for entry in unconverted] == ["BBB.L"]
    assert len(per_holding) == 1  # only AAA is valued; BBB is not double counted

    # Paired with a price-only holding the label becomes "mixed", not "price";
    # the share stays over the priced holdings only.
    fields = portfolio_utils._portfolio_return_basis(per_holding, unpriced)
    assert fields["portfolio_return_basis"] == MIXED_RETURN_BASIS
    assert fields["portfolio_price_basis_share"] == pytest.approx(1.0)
    assert fields["portfolio_unpriced_holdings"] == unpriced


def test_lone_fx_failed_total_return_holding_makes_basis_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no other non-cash holding, an FX-failed total-return holding labels the portfolio ``total``."""
    _patch_fx_failure(monkeypatch, {"BBB": TOTAL_RETURN_BASIS}, failing={"BBB"})

    per_holding, _unconverted, unpriced = portfolio_utils._gbp_holding_values(
        [("BBB", "L", 1.0)], 365, _FX_WINDOW, total_return=True
    )

    fields = portfolio_utils._portfolio_return_basis(per_holding, unpriced)
    assert per_holding == []
    assert fields["portfolio_return_basis"] == TOTAL_RETURN_BASIS
    assert fields["portfolio_price_basis_share"] is None


def test_fx_failed_holding_keeps_its_priced_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    """A price-basis FX-failed holding is listed as ``price`` even on the total-return path."""
    _patch_fx_failure(monkeypatch, {"AAA": TOTAL_RETURN_BASIS, "BBB": PRICE_RETURN_BASIS}, failing={"BBB"})

    per_holding, _unconverted, unpriced = portfolio_utils._gbp_holding_values(
        [("AAA", "L", 1.0), ("BBB", "L", 1.0)], 365, _FX_WINDOW, total_return=True
    )

    assert unpriced == [{"ticker": "BBB.L", "return_basis": PRICE_RETURN_BASIS}]
    fields = portfolio_utils._portfolio_return_basis(per_holding, unpriced)
    assert fields["portfolio_return_basis"] == MIXED_RETURN_BASIS


def test_fx_failed_cash_is_not_listed_as_unpriced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cash that fails FX conversion is reported as unconverted but stays out of ``unpriced``."""
    _patch_fx_failure(monkeypatch, {"CASH": None}, failing={"CASH"})

    per_holding, unconverted, unpriced = portfolio_utils._gbp_holding_values(
        [("CASH", "USD", 1.0)], 365, _FX_WINDOW, total_return=False
    )

    assert [entry["ticker"] for entry in unconverted] == ["CASH.USD"]  # the FX-failure path was taken
    assert per_holding == []
    assert unpriced == []
