"""The shared portfolio value series is valued in GBP (#7786).

``_holding_value_series`` feeds max drawdown, alpha and tracking error. It used
to sum units x each holding's *native* close, so pence lines counted 100x and
USD lines were summed as if they were pounds. These tests pin a GBX holding, a
USD holding and USD cash converting date by date with the stored FX history.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backend.common import instrument_api
from backend.common import portfolio_utils as pu

DAYS = [date(2024, 1, d) for d in range(1, 6)]  # Mon 1 Jan .. Fri 5 Jan 2024
REPORTING_DATE = DAYS[-1]

NATIVE_CLOSES = {
    ("GBXCO", "L"): [250.0, 260.0, 255.0, 250.0, 270.0],  # pence
    ("USCO", "N"): [100.0, 110.0, 90.0, 95.0, 100.0],  # dollars
}
CURRENCIES = {"GBXCO.L": "GBX", "USCO.N": "USD"}
# 2 Jan has no stored rate: 1 Jan's carries over the short gap.
USD_RATES = {date(2024, 1, 1): 0.8, date(2024, 1, 3): 0.75, date(2024, 1, 5): 0.7}

HOLDINGS = [
    {"ticker": "GBXCO.L", "units": 100},
    {"ticker": "USCO.N", "units": 10},
    {"ticker": "CASH.USD", "units": 1000},
]


def _fx_frame(rates: dict[date, float]) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime(list(rates)), "Rate": list(rates.values())})


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> dict[str, pd.DataFrame]:
    """An owner holding pence, dollar and USD-cash lines; returns the mutable FX store."""
    fx_store = {"USD": _fx_frame(USD_RATES)}

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda name, *, pricing_date=None, **_: {"accounts": [{"holdings": HOLDINGS}]},
    )
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda ticker, snapshot: tuple(ticker.split(".", 1)))
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        closes = NATIVE_CLOSES.get((ticker, exchange))
        if closes is None:
            return pd.DataFrame()  # cash has no stored series
        return pd.DataFrame({"Date": pd.to_datetime(DAYS), "Close": closes})

    def fake_load_fx_history(curr: str, start=None, end=None) -> pd.DataFrame:
        return fx_store.get(curr, pd.DataFrame(columns=["Date", "Rate"]))

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)
    monkeypatch.setattr(pu, "load_fx_history", fake_load_fx_history)
    monkeypatch.setattr(pu, "instrument_currency", lambda ticker, exchange: CURRENCIES[f"{ticker}.{exchange}"])
    monkeypatch.setattr(
        pu,
        "get_scaling_override",
        lambda ticker, exchange, requested_scaling: 0.01 if ticker == "GBXCO" else 1.0,
    )
    return fx_store


def _gbx_values() -> list[float]:
    return [100 * close * 0.01 for close in NATIVE_CLOSES[("GBXCO", "L")]]


def test_max_drawdown_series_values_gbx_and_usd_holdings_in_gbp(owner) -> None:
    value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    usd_rate = [0.8, 0.8, 0.75, 0.75, 0.7]  # stored rates, 2 Jan and 4 Jan carried forward
    usd_values = [10 * close * rate for close, rate in zip(NATIVE_CLOSES[("USCO", "N")], usd_rate)]
    cash_values = [1000 * rate for rate in usd_rate]
    expected = [g + u + c for g, u, c in zip(_gbx_values(), usd_values, cash_values)]

    assert [row["date"] for row in breakdown["series"]] == [d.isoformat() for d in DAYS]
    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(expected)
    assert expected == pytest.approx([1850.0, 1940.0, 1680.0, 1712.5, 1670.0])
    assert value == pytest.approx(1670.0 / 1940.0 - 1)
    assert breakdown["unconverted_holdings"] == []


def test_total_return_series_is_converted_after_reinvesting(owner, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_total_return_closes(closes: pd.Series, ticker: str, exchange: str):
        return closes * 1.1, "total"  # reinvested dividends, still in the native currency

    monkeypatch.setattr(pu, "total_return_closes", fake_total_return_closes)

    total, basis = pu._portfolio_return_series("steve", days=5, pricing_date=REPORTING_DATE)

    usd_rate = [0.8, 0.8, 0.75, 0.75, 0.7]
    usd_values = [10 * close * 1.1 * rate for close, rate in zip(NATIVE_CLOSES[("USCO", "N")], usd_rate)]
    gbx_values = [value * 1.1 for value in _gbx_values()]
    cash_values = [1000 * rate for rate in usd_rate]  # cash earns nothing on either basis
    expected = [g + u + c for g, u, c in zip(gbx_values, usd_values, cash_values)]

    assert list(total.to_numpy()) == pytest.approx(expected)
    assert basis["portfolio_return_basis"] == "total"
    assert basis["unconverted_holdings"] == []


def test_holdings_without_stored_fx_are_left_out_and_reported(owner) -> None:
    owner.clear()  # no USD history stored

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(_gbx_values())
    assert breakdown["unconverted_holdings"] == [
        {"ticker": "USCO.N", "currency": "USD", "reason": "no stored FX rate"},
        {"ticker": "CASH.USD", "currency": "USD", "reason": "no stored FX rate"},
    ]


def test_fx_gap_longer_than_the_fill_window_leaves_the_holding_out(owner) -> None:
    # The last stored rate is more than _MAX_FX_GAP_FILL_DAYS before 5 Jan.
    owner["USD"] = _fx_frame({date(2023, 12, 20): 0.8, date(2023, 12, 27): 0.8})

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(_gbx_values())
    assert {row["ticker"] for row in breakdown["unconverted_holdings"]} == {"USCO.N", "CASH.USD"}


def test_alpha_and_tracking_error_breakdowns_report_unconverted_holdings(owner, monkeypatch) -> None:
    owner.clear()
    bench = pd.Series([0.01, -0.01, 0.02, 0.0], index=DAYS[1:])
    monkeypatch.setattr(pu, "_benchmark_daily_returns", lambda *a, **k: (bench, "price"))

    _alpha, alpha_breakdown = pu.compute_alpha_vs_benchmark(
        "steve", "VWRL.L", days=5, include_breakdown=True, pricing_date=REPORTING_DATE
    )
    _te, te_breakdown = pu.compute_tracking_error(
        "steve", "VWRL.L", days=5, include_breakdown=True, pricing_date=REPORTING_DATE
    )

    for breakdown in (alpha_breakdown, te_breakdown):
        assert {row["ticker"] for row in breakdown["unconverted_holdings"]} == {"USCO.N", "CASH.USD"}


def test_gbp_series_matches_owner_performance_history_for_sterling_holdings(monkeypatch, owner) -> None:
    """With no FX involved the drawdown series and ``/performance/{owner}`` agree date for date."""
    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", _sterling_portfolio)

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)
    history = pu.compute_owner_performance("steve", days=5, pricing_date=REPORTING_DATE)["history"]

    assert [row["date"] for row in breakdown["series"]] == [row["date"] for row in history]
    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx([row["value"] for row in history])


def _sterling_portfolio(name: str, *, pricing_date=None, **_) -> dict:
    return {"accounts": [{"holdings": [{"ticker": "GBXCO.L", "units": 100}]}]}
