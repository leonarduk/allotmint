"""Tests for portfolio value series helpers."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pandas.testing as pdt

from backend.common import portfolio_utils as pu


def _make_df(values: list[tuple[str, float]]) -> pd.DataFrame:
    """Helper to build a ``Date``/``Close`` DataFrame from value tuples."""

    dates, closes = zip(*values)
    return pd.DataFrame({"Date": list(dates), "Close": list(closes)})


def test_portfolio_value_series_aggregates_and_skips_flagged(monkeypatch):
    import backend.common.instrument_api as instrument_api

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda name: {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "AAA.L", "units": "10"},
                        {"ticker": "BBB.N", "units": 5},
                        {"ticker": "FLAGGED.L", "units": 1},
                        {"ticker": "UNRESOLVED", "units": 3},
                    ]
                }
            ]
        },
    )

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: {
            "AAA.L": ("AAA", "L"),
            "BBB.N": ("BBB", "N"),
            "FLAGGED.L": ("FLAGGED", "L"),
        }.get(ticker),
    )

    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {"AAA.L": {}, "BBB.N": {}, "FLAGGED.L": {"flagged": True}},
        raising=False,
    )

    calls: list[tuple[str, str]] = []

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        calls.append((ticker, exchange))
        data_map = {
            ("AAA", "L"): _make_df([("2024-01-01", 100.0), ("2024-01-02", 110.0)]),
            ("BBB", "N"): _make_df([("2024-01-01", 20.0), ("2024-01-02", 22.0)]),
        }
        return data_map.get((ticker, exchange), pd.DataFrame())

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    result = pu._portfolio_value_series("owner-1", days=30)

    expected = pd.Series(
        [1100.0, 1210.0],
        index=[date(2024, 1, 1), date(2024, 1, 2)],
        dtype=float,
    )

    pdt.assert_series_equal(result, expected, check_names=False)

    assert ("UNRESOLVED", "L") in calls
    assert ("FLAGGED", "L") not in calls


def test_portfolio_value_series_uses_group_builder(monkeypatch):
    import backend.common.instrument_api as instrument_api

    def boom(*_args, **_kwargs):  # pragma: no cover - defensive
        raise AssertionError("owner builder should not be used")

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", boom)

    monkeypatch.setattr(
        pu.group_portfolio,
        "build_group_portfolio",
        lambda name: {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "XYZ.L", "units": 2},
                    ]
                }
            ]
        },
    )

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: {"XYZ.L": ("XYZ", "L")}.get(ticker),
    )

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: _make_df(
            [("2024-02-01", 50.0), ("2024-02-02", 55.0)]
        ),
    )

    result = pu._portfolio_value_series("group-1", days=10, group=True)

    expected = pd.Series(
        [100.0, 110.0],
        index=[date(2024, 2, 1), date(2024, 2, 2)],
        dtype=float,
    )

    pdt.assert_series_equal(result, expected, check_names=False)


def test_cash_value_series_sums_cash_holdings(monkeypatch):
    import backend.common.instrument_api as instrument_api

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda name: {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "CASH.GBP", "exchange": "GBP", "units": "1000"},
                        {"ticker": "CASH.USD", "exchange": "USD", "units": 500},
                        {"ticker": "EQUITY.L", "units": 1},
                    ]
                }
            ]
        },
    )

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: {
            "CASH.GBP": ("CASH_GBP", None),
            "CASH.USD": ("CASH_USD", None),
        }.get(ticker),
    )

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        data_map = {
            ("CASH_GBP", "GBP"): _make_df([("2024-03-01", 1.0), ("2024-03-02", 1.01)]),
            ("CASH_USD", "USD"): _make_df([("2024-03-01", 1.2), ("2024-03-02", 1.25)]),
        }
        return data_map.get((ticker, exchange), pd.DataFrame())

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    result = pu._cash_value_series("owner-2", days=60)

    expected = pd.Series(
        [1600.0, 1635.0],
        index=[date(2024, 3, 1), date(2024, 3, 2)],
        dtype=float,
    )

    pdt.assert_series_equal(result, expected, check_names=False)
