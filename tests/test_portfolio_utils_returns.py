import datetime as dt
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.common import instrument_api
from backend.common import portfolio_utils as pu


@pytest.fixture
def portfolio_series():
    base = date(2024, 1, 1)
    idx = pd.Index([base + timedelta(days=i) for i in range(3)])
    return pd.Series([1000.0, 1050.0, 1100.0], index=idx)


@pytest.fixture
def sample_transactions():
    return [
        {"date": "2024-01-02", "type": "deposit", "amount_minor": 1000},
        {"date": "2024-02-01", "kind": "withdrawal", "amount_minor": 500},
        {"date": "2023-12-15", "type": "deposit", "amount_minor": 2000},
    ]


def test_compute_time_weighted_return_with_cashflows(monkeypatch, portfolio_series, sample_transactions):
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: portfolio_series,
    )
    monkeypatch.setattr(
        pu,
        "load_transactions",
        lambda owner, *, scaffold_missing=False: sample_transactions,
    )

    result = pu.compute_time_weighted_return("owner")

    assert result == pytest.approx(0.089523, rel=1e-4)


def test_compute_time_weighted_return_requires_two_points(monkeypatch):
    idx = pd.Index([date(2024, 1, 1)])
    series = pd.Series([1000.0], index=idx)
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: [])

    assert pu.compute_time_weighted_return("owner") is None


@pytest.fixture
def one_year_series():
    start = date(2024, 1, 1)
    end = date(2025, 1, 1)
    idx = pd.Index([start, end])
    return pd.Series([1000.0, 1100.0], index=idx)


def test_compute_xirr_simple_contribution(monkeypatch, one_year_series):
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: one_year_series,
    )
    transactions = [
        {"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 100000},
        {"date": "2023-12-01", "type": "deposit", "amount_minor": 1000},
        {"date": "2025-02-01", "kind": "WITHDRAWAL", "amount_minor": 1000},
    ]
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: transactions)

    result = pu.compute_xirr("owner")

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_xirr_requires_cashflows(monkeypatch, one_year_series):
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: one_year_series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: [])

    assert pu.compute_xirr("owner") is None


def test_compute_cagr(monkeypatch, one_year_series):
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: one_year_series,
    )

    result = pu.compute_cagr("owner")

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_cagr_invalid_series(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    series = pd.Series([0.0, 1000.0], index=idx)
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: series,
    )

    assert pu.compute_cagr("owner") is None


def test_compute_cash_apy(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    cash_series = pd.Series([5000.0, 5250.0], index=idx)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: cash_series)

    result = pu.compute_cash_apy("owner")

    assert result == pytest.approx(0.05, abs=1e-3)


def test_compute_cash_apy_empty(monkeypatch):
    empty_series = pd.Series(dtype=float)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: empty_series)

    assert pu.compute_cash_apy("owner") is None


@pytest.fixture
def sample_portfolio():
    return {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "ABC", "units": "1.2", "exchange": "L"},
                    {"ticker": "ABC", "units": 0.8},  # missing exchange -> resolved
                    {"ticker": "MNO", "units": 5},  # price lookup will fail
                    {"ticker": "ZERO", "units": 0},  # zero units should be ignored
                ]
            },
            {
                "holdings": [
                    {"ticker": "DEF.US", "units": 2.3456},
                    {"ticker": "DEF", "units": "1.0", "exchange": "US"},
                ]
            },
        ]
    }


def test_portfolio_value_breakdown_aggregates_and_handles_missing(monkeypatch, sample_portfolio):
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: sample_portfolio,
    )

    resolved = {
        "ABC": ("ABC", "L"),
        "DEF.US": ("DEF", "US"),
        "DEF": ("DEF", "US"),
    }

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: resolved.get(ticker),
    )

    prices = {
        ("ABC", "L"): 10.12345,
        ("DEF", "US"): 50.98765,
    }

    def fake_get_price_for_date_scaled(ticker, exchange, target):
        price = prices.get((ticker, exchange))
        if price is None:
            return None, None
        return price, "test"

    monkeypatch.setattr(pu, "_get_price_for_date_scaled", fake_get_price_for_date_scaled)

    rows = pu.portfolio_value_breakdown("owner", "2024-05-01")

    rows_by_key = {(row["ticker"], row["exchange"]): row for row in rows}

    assert ("ZERO", "L") not in rows_by_key
    assert {key for key in rows_by_key} == {("ABC", "L"), ("DEF", "US"), ("MNO", "L")}

    abc = rows_by_key[("ABC", "L")]
    assert abc["units"] == pytest.approx(2.0)
    assert abc["price"] == pytest.approx(10.1235)
    assert abc["value"] == pytest.approx(20.25)

    deff = rows_by_key[("DEF", "US")]
    assert deff["units"] == pytest.approx(3.3456)
    assert deff["price"] == pytest.approx(50.9877)
    assert deff["value"] == pytest.approx(170.58)

    mno = rows_by_key[("MNO", "L")]
    assert mno["units"] == pytest.approx(5.0)
    assert mno["price"] is None
    assert mno["value"] is None


def test_portfolio_value_breakdown_invalid_date(monkeypatch):
    called = False

    def fake_builder(owner, *, pricing_date=None, **_):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", fake_builder)

    with pytest.raises(ValueError) as excinfo:
        pu.portfolio_value_breakdown("owner", "not-a-date")

    assert str(excinfo.value) == "Invalid date: not-a-date"
    assert called is False


def test_compute_owner_performance_respects_flagged_and_cash(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "FLAG.L", "units": 1},
                    {"ticker": "NORM.L", "units": 1},
                    {"ticker": "CASH.GBP", "units": 1},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {
            "FLAG.L": {"flagged": True},
            "NORM.L": {"flagged": False},
            "CASH.GBP": {"flagged": False},
        },
        raising=False,
    )

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    frames = {
        ("FLAG", "L"): pd.DataFrame({"Date": dates, "Close": [5.0, 6.0]}),
        ("NORM", "L"): pd.DataFrame({"Date": dates, "Close": [10.0, 11.0]}),
        ("CASH", "GBP"): pd.DataFrame({"Date": dates, "Close": [0.01, 0.01]}),
    }

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return frames.get((ticker, exchange), pd.DataFrame()).copy()

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    excluded = pu.compute_owner_performance("owner", days=10, include_flagged=False, include_cash=False)
    included_flagged = pu.compute_owner_performance("owner", days=10, include_flagged=True, include_cash=False)
    included_cash = pu.compute_owner_performance("owner", days=10, include_flagged=False, include_cash=True)

    assert [row["value"] for row in excluded["history"]] == [10.0, 11.0]
    assert [row["value"] for row in included_flagged["history"]] == [15.0, 17.0]
    assert [row["value"] for row in included_cash["history"]] == [11.0, 12.0]

    for payload in (excluded, included_flagged, included_cash):
        assert "reporting_date" in payload
        assert "previous_date" in payload
        date.fromisoformat(payload["reporting_date"])
        date.fromisoformat(payload["previous_date"])


def test_compute_owner_performance_forward_fills_exchange_holiday(monkeypatch):
    """Regression test for #6857: a single-exchange holiday (e.g. a UK bank
    holiday closing an LSE-listed holding while a NYSE-listed holding in the
    same portfolio keeps trading) must not be treated as the closed holding
    being worth £0 that day. Runs unconditionally in OSS CI -- no
    ``allotmint_pro`` required.
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "LSE.L", "units": 10},
                    {"ticker": "NYSE.N", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=3, freq="D")  # Mon, Tue, Wed
    # LSE.L has no row for the middle date (bank holiday); NYSE.N trades every day.
    lse_dates = pd.DatetimeIndex([all_dates[0], all_dates[2]])
    frames = {
        ("LSE", "L"): pd.DataFrame({"Date": lse_dates, "Close": [100.0, 102.0]}),
        ("NYSE", "N"): pd.DataFrame({"Date": all_dates, "Close": [50.0, 51.0, 52.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 100.0 + 5 * 50.0,  # 1250: both priced
            10 * 100.0 + 5 * 51.0,  # 1255: LSE.L holiday -> carries forward 100.0, not 0
            10 * 102.0 + 5 * 52.0,  # 1280: LSE.L reopens
        ]
    )
    # No fake crash-and-recover: the middle value sits between its
    # neighbours instead of collapsing toward zero.
    assert values[0] < values[1] < values[2]


def test_compute_owner_performance_forward_fills_multi_day_gap(monkeypatch):
    """Regression test for #6857: multi-day gaps (e.g. a Christmas/New Year
    week where one exchange is shut for several consecutive days) must also
    forward-fill correctly, not just single-day gaps.
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "LSE.L", "units": 10},
                    {"ticker": "NYSE.N", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=4, freq="D")  # Mon-Thu
    # LSE.L is shut for the middle two days (e.g. a holiday week); NYSE.N trades every day.
    lse_dates = pd.DatetimeIndex([all_dates[0], all_dates[3]])
    frames = {
        ("LSE", "L"): pd.DataFrame({"Date": lse_dates, "Close": [100.0, 104.0]}),
        ("NYSE", "N"): pd.DataFrame({"Date": all_dates, "Close": [50.0, 51.0, 52.0, 53.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 100.0 + 5 * 50.0,  # 1050
            10 * 100.0 + 5 * 51.0,  # 1255: LSE.L still shut -> carries forward 100.0
            10 * 100.0 + 5 * 52.0,  # 1260: LSE.L still shut -> carries forward 100.0
            10 * 104.0 + 5 * 53.0,  # 1305: LSE.L reopens
        ]
    )


def test_compute_owner_performance_leading_gap_contributes_zero(monkeypatch):
    """Regression test for #6857: a ticker with no price history yet at the
    start of the requested window should contribute 0 for those dates, not
    NaN (and not be forward-filled from nothing).
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "OLD.L", "units": 10},
                    {"ticker": "NEW.L", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=3, freq="D")  # Mon, Tue, Wed
    new_dates = pd.DatetimeIndex([all_dates[2]])  # NEW.L only starts trading on day 3
    frames = {
        ("OLD", "L"): pd.DataFrame({"Date": all_dates, "Close": [10.0, 11.0, 12.0]}),
        ("NEW", "L"): pd.DataFrame({"Date": new_dates, "Close": [20.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 10.0,  # NEW.L not trading yet -> contributes 0, not NaN
            10 * 11.0,
            10 * 12.0 + 5 * 20.0,
        ]
    )
    assert all(v == v for v in values)  # no NaNs leaked through


def test_compute_owner_performance_filters_single_day_zero(monkeypatch):
    pytest.importorskip("allotmint_pro")
    portfolio = {"accounts": [{"holdings": [{"ticker": "ERR.L", "units": 10}]}]}

    real_calc = pu.PricingDateCalculator

    def fake_calc(*args, **kwargs):
        return real_calc(today=dt.date(2024, 1, 10))

    monkeypatch.setattr(pu, "PricingDateCalculator", fake_calc)

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    frames = {
        ("ERR", "L"): pd.DataFrame({"Date": dates, "Close": [100.0, 0.0, 102.0]}),
    }

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return frames.get((ticker, exchange), pd.DataFrame()).copy()

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result["history"][0]["value"] == pytest.approx(1000.0)
    assert result["history"][1]["value"] == pytest.approx(1010.0)
    assert result["history"][2]["value"] == pytest.approx(1020.0)

    issues = result["data_quality_issues"]
    assert issues == [
        {
            "date": "2024-01-02",
            "value": 0.0,
            "repaired_value": 1010.0,
            "previous_value": 1000.0,
            "next_value": 1020.0,
        }
    ]


def test_compute_owner_performance_drops_partial_close_nans(monkeypatch):
    pytest.importorskip("allotmint_pro")
    portfolio = {"accounts": [{"holdings": [{"ticker": "NAN.L", "units": 2}, {"ticker": "CASH.GBP", "units": 1}]}]}
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    frames = {
        ("NAN", "L"): pd.DataFrame({"Date": dates, "Close": [10.0, float("nan"), 11.0]}),
        ("CASH", "GBP"): pd.DataFrame({"Date": dates, "Close": [0.01, 99.0, 1.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames[(ticker, exchange)].copy(),
    )

    result = pu.compute_owner_performance("owner", days=10, include_cash=True)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert [row["value"] for row in result["history"]] == [21.0, 22.0, 23.0]


def test_cash_flow_signs_treat_dividend_singular_same_as_plural():
    """Regression test for #4948: backend/common/dividends.py writes the
    ``DIVIDEND`` (singular) transaction type, but the TWR/XIRR cash-flow sign
    table previously only recognised ``DIVIDENDS`` (plural), silently
    excluding automated dividend transactions from return calculations.
    """

    assert "DIVIDEND" in pu._CASH_FLOW_SIGNS
    assert pu._CASH_FLOW_SIGNS["DIVIDEND"] == pu._CASH_FLOW_SIGNS["DIVIDENDS"]


def test_group_transactions_merges_members_and_skips_missing(monkeypatch):
    """#7228: group TWR/XIRR need cash flows pooled across every member,
    the same way the group portfolio pools holdings.
    """

    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy", "ghost"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
        "lucy": [{"date": "2024-01-03", "type": "withdrawal", "amount_minor": 200}],
    }

    def fake_load_transactions(owner, *, scaffold_missing=False):
        if owner not in per_owner_txs:
            raise FileNotFoundError(owner)
        return per_owner_txs[owner]

    monkeypatch.setattr(pu, "load_transactions", fake_load_transactions)

    merged = pu._group_transactions("all")

    assert merged == per_owner_txs["steve"] + per_owner_txs["lucy"]


def test_compute_owner_performance_group_uses_group_portfolio(monkeypatch):
    """#7228: with group=True the group aggregation helper (the same one
    /portfolio-group/{slug} uses) supplies the combined holdings instead of
    a single owner's holdings -- the owner-scoped path must be untouched.
    """

    group_portfolio_dict = {
        "accounts": [{"holdings": [{"ticker": "NORM.L", "units": 3}]}],
    }

    def unexpected_owner_lookup(owner, *, pricing_date=None, **_):
        raise AssertionError("group=True must not call build_owner_portfolio")

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", unexpected_owner_lookup)
    monkeypatch.setattr(
        pu.group_portfolio,
        "build_group_portfolio",
        lambda slug, *, pricing_date=None: group_portfolio_dict if slug == "all" else {},
    )
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    frame = pd.DataFrame({"Date": dates, "Close": [10.0, 11.0]})
    monkeypatch.setattr(pu, "load_meta_timeseries", lambda ticker, exchange, days: frame.copy())

    result = pu.compute_owner_performance("all", days=10, group=True)

    assert [row["value"] for row in result["history"]] == [30.0, 33.0]


def test_compute_owner_performance_group_unknown_slug_raises(monkeypatch):
    def raise_unknown(slug, *, pricing_date=None):
        raise ValueError(f"Unknown group slug: {slug!r}")

    monkeypatch.setattr(pu.group_portfolio, "build_group_portfolio", raise_unknown)

    with pytest.raises(ValueError):
        pu.compute_owner_performance("bogus", group=True)


def test_compute_time_weighted_return_group_pools_member_cashflows(monkeypatch, portfolio_series):
    def fake_series(name, days=365, *, group=False, pricing_date=None):
        assert name == "all"
        assert group is True
        return portfolio_series

    monkeypatch.setattr(pu, "_portfolio_value_series", fake_series)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
        "lucy": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
    }
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: per_owner_txs[owner])

    # Same series with double the single-owner deposit pooled across both
    # members on the same day should differ from the single-owner result.
    group_result = pu.compute_time_weighted_return("all", group=True)

    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda name, days=365, *, group=False, pricing_date=None: portfolio_series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: per_owner_txs["steve"])
    owner_result = pu.compute_time_weighted_return("steve")

    assert group_result is not None
    assert owner_result is not None
    assert group_result != owner_result


def test_compute_xirr_group_pools_member_cashflows(monkeypatch, one_year_series):
    def fake_series(name, days=365, *, group=False, pricing_date=None):
        assert name == "all"
        assert group is True
        return one_year_series

    monkeypatch.setattr(pu, "_portfolio_value_series", fake_series)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 50000}],
        "lucy": [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 50000}],
    }
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: per_owner_txs[owner])

    result = pu.compute_xirr("all", group=True)

    assert result == pytest.approx(0.10, abs=1e-3)
