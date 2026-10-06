"""Portfolio value series are valued in GBP (#7786, #9678).

``_holding_value_series`` feeds max drawdown, alpha and tracking error, and
``compute_owner_performance`` backs ``/performance/{owner}``. Both used to sum
units x a native close: the former with no pence scaling or FX, the latter with
pence scaling but no FX. They now share one GBP valuation path
(``_gbp_holding_values``). These tests pin a GBX holding, a USD holding and USD
cash converting date by date with the stored FX history, and the two endpoints
agreeing on that mixed-currency portfolio.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import instrument_api
from backend.common import portfolio_utils as pu
from backend.timeseries import cache

DAYS = [date(2024, 1, d) for d in range(1, 6)]  # Mon 1 Jan .. Fri 5 Jan 2024
REPORTING_DATE = DAYS[-1]

NATIVE_CLOSES = {
    ("GBXCO", "L"): [250.0, 260.0, 255.0, 250.0, 270.0],  # pence
    ("USCO", "N"): [100.0, 110.0, 90.0, 95.0, 100.0],  # dollars
}
CURRENCIES = {"GBXCO.L": "GBX", "USCO.N": "USD"}
# 2 Jan and 4 Jan have no stored rate: the previous day's carries over.
USD_RATES = {date(2024, 1, 1): 0.8, date(2024, 1, 3): 0.75, date(2024, 1, 5): 0.7}
USD_RATE_BY_DAY = [0.8, 0.8, 0.75, 0.75, 0.7]

GBX_LINE = {"ticker": "GBXCO.L", "units": 100}
USD_LINE = {"ticker": "USCO.N", "units": 10}
USD_CASH = {"ticker": "CASH.USD", "units": 1000}


def _fx_frame(rates: dict[date, float]) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime(list(rates)), "Rate": list(rates.values())})


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """An owner (and group) holding pence, dollar and USD-cash lines.

    ``world.holdings`` and ``world.fx`` (currency -> stored rates) can be
    changed by a test before it computes anything.
    """
    state = SimpleNamespace(holdings=[GBX_LINE, USD_LINE, USD_CASH], fx={"USD": _fx_frame(USD_RATES)})

    def portfolio(name, *, pricing_date=None, **_):
        return {"accounts": [{"holdings": state.holdings}]}

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        closes = NATIVE_CLOSES.get((ticker, exchange))
        if closes is None:
            return pd.DataFrame()  # cash has no stored series
        return pd.DataFrame({"Date": pd.to_datetime(DAYS), "Close": closes})

    def fake_load_fx_history(curr: str, start=None, end=None) -> pd.DataFrame:
        return state.fx.get(curr, pd.DataFrame(columns=["Date", "Rate"]))

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", portfolio)
    monkeypatch.setattr(pu.group_portfolio, "build_group_portfolio", portfolio)
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda ticker, snapshot: tuple(ticker.split(".", 1)))
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)
    monkeypatch.setattr(pu, "load_fx_history", fake_load_fx_history)
    monkeypatch.setattr(pu, "instrument_currency", lambda ticker, exchange: CURRENCIES[f"{ticker}.{exchange}"])
    monkeypatch.setattr(
        pu,
        "get_scaling_override",
        lambda ticker, exchange, requested_scaling: 0.01 if ticker == "GBXCO" else 1.0,
    )
    return state


def _gbx_values() -> list[float]:
    return [100 * close * 0.01 for close in NATIVE_CLOSES[("GBXCO", "L")]]


def _usd_values() -> list[float]:
    return [10 * close * rate for close, rate in zip(NATIVE_CLOSES[("USCO", "N")], USD_RATE_BY_DAY)]


def _cash_values() -> list[float]:
    return [1000 * rate for rate in USD_RATE_BY_DAY]


def _sum(*columns: list[float]) -> list[float]:
    return [sum(values) for values in zip(*columns)]


def test_max_drawdown_series_values_gbx_and_usd_holdings_in_gbp(world) -> None:
    value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    expected = _sum(_gbx_values(), _usd_values(), _cash_values())
    assert [row["date"] for row in breakdown["series"]] == [d.isoformat() for d in DAYS]
    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(expected)
    assert expected == pytest.approx([1850.0, 1940.0, 1680.0, 1712.5, 1670.0])
    assert value == pytest.approx(1670.0 / 1940.0 - 1)
    assert breakdown["unconverted_holdings"] == []


def test_owner_performance_agrees_with_max_drawdown_for_gbx_usd_and_usd_cash(world) -> None:
    """``compute_owner_performance`` values through the same GBP path (#9678)."""
    value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)
    perf = pu.compute_owner_performance("steve", days=5, pricing_date=REPORTING_DATE)

    assert [row["date"] for row in perf["history"]] == [row["date"] for row in breakdown["series"]]
    assert [row["value"] for row in perf["history"]] == pytest.approx(
        [row["portfolio_value"] for row in breakdown["series"]], abs=0.005
    )
    assert perf["history"][-1]["value"] == pytest.approx(1670.0)
    assert perf["max_drawdown"] == pytest.approx(value)
    assert perf["unconverted_holdings"] == []


def test_owner_performance_leaves_out_and_reports_holdings_without_fx(world) -> None:
    world.fx.clear()

    perf = pu.compute_owner_performance("steve", days=5, pricing_date=REPORTING_DATE)

    assert [row["value"] for row in perf["history"]] == pytest.approx(_gbx_values())
    assert {row["ticker"] for row in perf["unconverted_holdings"]} == {"USCO.N", "CASH.USD"}


def test_total_return_series_is_converted_after_reinvesting(world, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_total_return_closes(closes: pd.Series, ticker: str, exchange: str):
        return closes * 1.1, "total"  # reinvested dividends, still in the native currency

    monkeypatch.setattr(pu, "total_return_closes", fake_total_return_closes)

    total, basis = pu._portfolio_return_series("steve", days=5, pricing_date=REPORTING_DATE)

    # Cash earns nothing on either basis.
    expected = _sum([v * 1.1 for v in _gbx_values()], [v * 1.1 for v in _usd_values()], _cash_values())
    assert list(total.to_numpy()) == pytest.approx(expected)
    assert basis["portfolio_return_basis"] == "total"
    assert basis["unconverted_holdings"] == []


def test_holdings_without_stored_fx_are_left_out_and_reported(world) -> None:
    world.fx.clear()  # no USD history stored

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(_gbx_values())
    left_out = {"currency": "USD", "reason": pu.FX_MISSING_ALL_DATES, "missing_fx_days": 5}
    window = {"first": "2024-01-01", "last": "2024-01-05"}
    assert breakdown["unconverted_holdings"] == [
        {"ticker": "USCO.N", **left_out, **window},
        {"ticker": "CASH.USD", **left_out, **window},
    ]


def test_fx_older_than_the_fill_window_on_every_date_leaves_the_holding_out(world) -> None:
    # The only stored rate is more than _MAX_FX_GAP_FILL_DAYS before 1 Jan.
    world.fx["USD"] = _fx_frame({date(2023, 12, 20): 0.8})

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)

    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(_gbx_values())
    assert {row["ticker"] for row in breakdown["unconverted_holdings"]} == {"USCO.N", "CASH.USD"}
    assert {row["reason"] for row in breakdown["unconverted_holdings"]} == {pu.FX_MISSING_ALL_DATES}


def test_partial_fx_gap_keeps_the_holding_and_treats_those_dates_as_missing_prices(world) -> None:
    """A rate for 1 Jan only: 2-5 Jan have none (27 Dec + 5 days covers 1 Jan alone).

    The holding stays in both series. Its 2-5 Jan values are missing, so each
    endpoint applies its own gap rule for missing prices: the series path
    carries 1 Jan for up to 5 rows, ``compute_owner_performance`` carries it
    without limit -- the same within this window.
    """
    world.fx["USD"] = _fx_frame({date(2023, 12, 27): 0.8})

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)
    perf = pu.compute_owner_performance("steve", days=5, pricing_date=REPORTING_DATE)

    usd_first_day = 10 * NATIVE_CLOSES[("USCO", "N")][0] * 0.8 + 1000 * 0.8  # line + cash on 1 Jan
    expected = [gbx + usd_first_day for gbx in _gbx_values()]
    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx(expected)
    assert [row["value"] for row in perf["history"]] == pytest.approx(expected, abs=0.005)
    partial = {"currency": "USD", "reason": pu.FX_MISSING_SOME_DATES, "missing_fx_days": 4}
    window = {"first": "2024-01-02", "last": "2024-01-05"}
    expected_report = [{"ticker": "USCO.N", **partial, **window}, {"ticker": "CASH.USD", **partial, **window}]
    assert breakdown["unconverted_holdings"] == expected_report
    assert perf["unconverted_holdings"] == expected_report


def test_duplicate_fx_dates_use_the_last_stored_rate(world) -> None:
    world.fx["USD"] = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-03"]),
            "Rate": [0.6, 0.8, 0.75],
        }
    )

    rates = pu._gbp_rates("USD", pd.Index([date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]))

    assert list(rates.to_numpy()) == [0.8, 0.75, 0.75]


def test_gbx_only_portfolio_is_valued_in_pounds_by_both_endpoints(world) -> None:
    """The reported bug: pence lines were summed as pounds, ~100x the dashboard.

    On ``main`` before #7786 the max-drawdown series read 25,000 here.
    """
    world.holdings = [GBX_LINE]
    client = TestClient(create_app())
    query = f"days=5&as_of={REPORTING_DATE.isoformat()}"

    drawdown = client.get(f"/performance/steve/max-drawdown?{query}").json()
    perf = client.get(f"/performance/steve?{query}").json()

    pounds = [100 * close / 100 for close in NATIVE_CLOSES[("GBXCO", "L")]]  # units x pence / 100
    assert [row["portfolio_value"] for row in drawdown["series"]] == pytest.approx(pounds)
    _assert_endpoints_agree(perf, drawdown, expected_final=270.0)


def test_fx_rate_exactly_at_the_fill_window_is_used_and_one_day_older_is_not(world) -> None:
    day = date(2024, 1, 10)
    assert pu._MAX_FX_GAP_FILL_DAYS == 5

    world.fx["USD"] = _fx_frame({date(2024, 1, 5): 0.8})  # exactly 5 days old
    assert list(pu._gbp_rates("USD", pd.Index([day])).to_numpy()) == [0.8]

    world.fx["USD"] = _fx_frame({date(2024, 1, 4): 0.8})  # 6 days old
    assert pd.isna(pu._gbp_rates("USD", pd.Index([day])).iloc[0])


def test_gbp_rates_align_with_an_unsorted_index(world) -> None:
    index = pd.Index([date(2024, 1, 5), date(2024, 1, 1), date(2024, 1, 3)])

    rates = pu._gbp_rates("USD", index)

    assert list(rates.index) == list(index)
    assert list(rates.to_numpy()) == [0.7, 0.8, 0.75]


def test_weekday_cash_is_carried_over_a_weekend_close_of_another_holding() -> None:
    """Cash is synthesised on business days only; a holding priced on a Saturday keeps the cash in that day's total."""
    cash = pu._cash_closes(date(2024, 1, 4), date(2024, 1, 8)) * 1000.0  # Thu, Fri, Mon
    saturday = date(2024, 1, 6)
    traded = pd.Series([10.0, 11.0, 12.0], index=[date(2024, 1, 5), saturday, date(2024, 1, 8)])

    total = pu._sum_holding_values([cash, traded], 0, date(2024, 1, 8))

    assert saturday not in cash.index
    assert total.loc[saturday] == pytest.approx(1011.0)


def test_unknown_currency_follows_the_loader_convention(monkeypatch: pytest.MonkeyPatch) -> None:
    """No metadata currency and an exchange outside ``EXCHANGE_TO_CCY`` count as GBP.

    That is what ``cache.instrument_currency`` returns, and so what the
    timeseries loader's FX step (and hence ``ledger_performance.load_gbp_closes``)
    assumes; the value series matches it rather than inventing its own rule.
    A known foreign exchange with no metadata still maps to its currency.
    """
    monkeypatch.setattr(cache, "get_instrument_meta", lambda ticker: {})
    monkeypatch.setattr(pu, "instrument_currency", cache.instrument_currency)

    assert pu._holding_currency("MYSTERY", "ZZ").canonical == cache.instrument_currency("MYSTERY", "ZZ") == "GBP"
    assert pu._holding_currency("USCO", "N").canonical == "USD"
    assert pu._holding_currency("CASH", "USD").canonical == "USD"
    assert pu._holding_currency("EUR", "CASH").canonical == "EUR"


def test_alpha_and_tracking_error_breakdowns_report_unconverted_holdings(world, monkeypatch) -> None:
    world.fx.clear()
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


def test_gbp_series_matches_owner_performance_history_for_sterling_holdings(world) -> None:
    """With no FX involved the drawdown series and ``/performance/{owner}`` agree date for date."""
    world.holdings = [GBX_LINE]

    _value, breakdown = pu.compute_max_drawdown("steve", days=5, include_breakdown=True, pricing_date=REPORTING_DATE)
    history = pu.compute_owner_performance("steve", days=5, pricing_date=REPORTING_DATE)["history"]

    assert [row["date"] for row in breakdown["series"]] == [row["date"] for row in history]
    assert [row["portfolio_value"] for row in breakdown["series"]] == pytest.approx([row["value"] for row in history])


# ──────────────────────────────────────────────────────────────
# Route level: the two endpoints agree on a mixed-currency portfolio
# ──────────────────────────────────────────────────────────────
def _assert_endpoints_agree(perf: dict, drawdown: dict, expected_final: float) -> None:
    series = drawdown["series"]
    assert [row["date"] for row in perf["history"]] == [row["date"] for row in series]
    assert [row["value"] for row in perf["history"]] == pytest.approx(
        [row["portfolio_value"] for row in series], abs=0.005
    )
    assert perf["history"][-1]["value"] == pytest.approx(expected_final)
    assert perf["max_drawdown"] == pytest.approx(drawdown["max_drawdown"])
    assert perf["unconverted_holdings"] == drawdown["unconverted_holdings"] == []


def test_owner_routes_agree_for_gbx_usd_and_usd_cash(world) -> None:
    client = TestClient(create_app())
    query = f"days=5&as_of={REPORTING_DATE.isoformat()}"

    perf = client.get(f"/performance/steve?{query}")
    drawdown = client.get(f"/performance/steve/max-drawdown?{query}")

    assert perf.status_code == drawdown.status_code == 200
    _assert_endpoints_agree(perf.json(), drawdown.json(), expected_final=1670.0)


def test_group_routes_agree_for_gbx_and_usd_holdings(world) -> None:
    """``/performance-group/{slug}/max-drawdown`` takes no ``as_of``, so the window ends today.

    Cash is synthesised over that window, which these fixed 2024 closes do not
    reach, so the group fixture holds the GBX and USD lines only.
    """
    world.holdings = [GBX_LINE, USD_LINE]
    client = TestClient(create_app())

    perf = client.get("/performance-group/family?days=5")
    drawdown = client.get("/performance-group/family/max-drawdown?days=5")

    assert perf.status_code == drawdown.status_code == 200
    _assert_endpoints_agree(perf.json(), drawdown.json(), expected_final=_sum(_gbx_values(), _usd_values())[-1])
