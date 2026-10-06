"""An alternate exchange listing as an instrument's price source (#9657).

yfinance, the FX store and instrument metadata are all faked; a socket guard
fails any test that tries to reach the network.
"""

from __future__ import annotations

import importlib
import logging
import socket
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from backend.timeseries import alternate_listing
from backend.timeseries import fetch_meta_timeseries as fmt
from backend.timeseries.alternate_listing import (
    FX_FFILL_DAYS,
    MODE_FILL_GAPS,
    MODE_PRIMARY,
    PriceSource,
    apply_price_source,
    convert_prices,
    fetch_with_price_source,
    overlay_alternate_listing,
    parse_price_source,
    validate_price_source,
)
from backend.timeseries.source_basis import (
    alternate_listing_source,
    compatible_rows,
    is_alternate_listing_source,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

LABEL = "Yahoo:AIGE.MI→USD"
AIGE_META = {
    "ticker": "AIGE.L",
    "exchange": "L",
    "currency": "USD",
    "name": "WisdomTree Energy",
    "price_source": {"ticker": "AIGE", "exchange": "MI", "currency": "EUR"},
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class FakeTicker:
    """Stands in for ``yfinance.Ticker``."""

    def __init__(self, history: pd.DataFrame, currency: str = "EUR"):
        self._history = history
        self.history_metadata = {"currency": currency}

    def history(self, **kwargs):
        assert kwargs["auto_adjust"] is False and kwargs["actions"] is True
        start, end = pd.Timestamp(kwargs["start"]), pd.Timestamp(kwargs["end"])
        return self._history[(self._history.index >= start) & (self._history.index < end)]


def _yahoo_frame(days, closes, volume=100.0, dividends=None) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": volume},
        index=pd.DatetimeIndex(pd.to_datetime(days), name="Date"),
    )
    frame["Dividends"] = dividends if dividends is not None else 0.0
    frame["Stock Splits"] = 0.0
    return frame


def _install_yahoo(monkeypatch, history: pd.DataFrame, currency: str = "EUR") -> list[str]:
    calls: list[str] = []

    def factory(symbol):
        calls.append(symbol)
        return FakeTicker(history, currency)

    monkeypatch.setattr(alternate_listing.yf, "Ticker", factory)
    return calls


def _install_fx(monkeypatch, rates: dict[str, dict[str, float]]) -> None:
    def load(currency, start, end):
        table = rates.get(currency, {})
        frame = pd.DataFrame({"Date": pd.to_datetime(list(table)), "Rate": list(table.values())})
        if frame.empty:
            return frame
        days = frame["Date"].dt.date
        return frame[(days >= start) & (days <= end)].reset_index(drop=True)

    monkeypatch.setattr(alternate_listing, "_load_fx", load)


def _rows(days, closes, *, source="Yahoo", volume=100.0, ticker="AIGE.L") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(days),
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": volume,
            "Ticker": ticker,
            "Source": source,
        }
    )[STANDARD_COLUMNS]


# ── metadata ──────────────────────────────────────────────────


def test_parse_reads_the_block_and_defaults_currency_from_exchange():
    meta = {**AIGE_META, "price_source": {"ticker": "aige.mi", "exchange": "mi"}}
    assert parse_price_source(meta, own="AIGE.L") == PriceSource("AIGE", "MI", "EUR")
    assert parse_price_source({"currency": "USD"}) is None


def test_parse_reads_the_mode_and_defaults_to_fill_gaps():
    assert parse_price_source(AIGE_META, own="AIGE.L").mode == MODE_FILL_GAPS
    primary = {**AIGE_META, "price_source": {**AIGE_META["price_source"], "mode": "primary"}}
    assert parse_price_source(primary, own="AIGE.L").mode == MODE_PRIMARY


@pytest.mark.parametrize(
    ("block", "currency", "problem"),
    [
        ({"ticker": "AIGE", "exchange": "MOON"}, "USD", "unsupported exchange"),
        ({"ticker": "../x", "exchange": "MI"}, "USD", "invalid ticker"),
        ({"ticker": "AIGE", "exchange": "L"}, "USD", "own listing"),
        ({"ticker": "AIGE", "exchange": "MI", "currency": "GBp"}, "USD", "currency 'GBp'"),
        ({"ticker": "AIGE", "exchange": "MI"}, "GBX", "instrument currency"),
        ("AIGE.MI", "USD", "JSON object"),
        ({"ticker": "AIGE", "exchange": "MI", "mode": "first"}, "USD", "mode 'first'"),
        ({"ticker": "AIGE", "exchange": "MI", "mode": "PRIMARY"}, "USD", "mode 'PRIMARY'"),
    ],
)
def test_validate_reports_bad_blocks(block, currency, problem):
    problems = validate_price_source({"currency": currency, "price_source": block}, own="AIGE.L")
    assert any(problem in p for p in problems), problems
    with pytest.raises(ValueError):
        parse_price_source({"currency": currency, "price_source": block}, own="AIGE.L")


def test_source_label_round_trips():
    assert alternate_listing_source("aige.mi", "usd") == LABEL
    assert is_alternate_listing_source(LABEL)
    for other in ("Yahoo", "Stooq", "Yahoo:AIGE.MI", None, 1.0):
        assert not is_alternate_listing_source(other)


# ── conversion maths and FX gaps ──────────────────────────────


def test_convert_uses_same_date_cross_rate_and_rounds_to_six_figures(monkeypatch):
    _install_fx(
        monkeypatch,
        {"EUR": {"2026-09-01": 0.85, "2026-09-02": 0.86}, "USD": {"2026-09-01": 0.75, "2026-09-02": 0.74}},
    )
    prices = _rows(["2026-09-01", "2026-09-02"], [5.0, 5.123456789], ticker="AIGE.MI")

    out = convert_prices(prices, from_ccy="EUR", to_ccy="USD", source=LABEL)

    # EUR -> USD is EUR_rate / USD_rate (both GBP per unit) on the same date.
    assert out["Close"].tolist() == [round(5.0 * 0.85 / 0.75, 5), float(f"{5.123456789 * 0.86 / 0.74:.6g}")]
    assert out["Open"].tolist() == out["Close"].tolist()
    assert out["Volume"].tolist() == [100.0, 100.0]
    assert set(out["Source"]) == {LABEL}


def test_convert_carries_fx_forward_a_few_days_only_and_never_invents(monkeypatch, caplog):
    friday = date(2026, 9, 4)
    _install_fx(monkeypatch, {"EUR": {"2026-09-04": 0.86}, "USD": {"2026-09-04": 0.74}})
    within = friday + timedelta(days=FX_FFILL_DAYS)
    beyond = friday + timedelta(days=FX_FFILL_DAYS + 1)
    before = friday - timedelta(days=1)
    prices = _rows([before, friday, within, beyond], [5.0, 5.0, 5.0, 5.0], ticker="AIGE.MI")

    with caplog.at_level(logging.WARNING):
        out = convert_prices(prices, from_ccy="EUR", to_ccy="USD", source=LABEL)

    assert [d.date() for d in pd.to_datetime(out["Date"])] == [friday, within]
    assert out["Close"].tolist() == [float(f"{5.0 * 0.86 / 0.74:.6g}")] * 2
    assert "Dropping 2" in caplog.text


def test_convert_to_or_from_gbp_needs_one_rate(monkeypatch):
    _install_fx(monkeypatch, {"EUR": {"2026-09-01": 0.85}})
    prices = _rows(["2026-09-01"], [10.0], ticker="X.MI")
    assert convert_prices(prices, from_ccy="EUR", to_ccy="GBP", source="s")["Close"].tolist() == [8.5]
    assert convert_prices(prices, from_ccy="GBP", to_ccy="EUR", source="s")["Close"].tolist() == [
        float(f"{10 / 0.85:.6g}")
    ]


def test_convert_with_no_stored_fx_drops_everything(monkeypatch):
    _install_fx(monkeypatch, {})
    prices = _rows(["2026-09-01"], [10.0], ticker="X.MI")
    assert convert_prices(prices, from_ccy="EUR", to_ccy="USD", source="s").empty


# ── merge rule ────────────────────────────────────────────────


def test_overlay_keeps_real_native_rows_and_fills_everything_else():
    days = pd.bdate_range("2026-09-01", periods=6)
    converted = _rows(days, [5.0, 5.1, 5.2, 5.3, 5.4, 5.5], source=LABEL, volume=50.0)
    extra = _rows(["2026-09-09"], [float("nan")], source=LABEL)  # no close on the other listing either
    converted = pd.concat([converted, extra], ignore_index=True)
    native = pd.concat(
        [
            _rows(days[:1], [5.01]),  # real close and volume: kept
            _rows(days[1:2], [float("nan")], volume=202.0),  # no close: converted
            _rows(days[2:3], [5.19], volume=0.0),  # no volume: converted
        ]
    )
    # A stored native row with a real close is not overwritten even though
    # this fetch did not return it; an earlier converted row is not "native".
    stored = pd.concat([_rows(days[3:4], [5.31]), _rows(days[4:5], [5.39], source=LABEL)])

    out = overlay_alternate_listing(native, stored, converted, label="AIGE.L").set_index("Date")

    assert list(out.index) == [days[0], days[1], days[2], days[4], days[5]]
    assert out.loc[days[0], "Source"] == "Yahoo" and out.loc[days[0], "Close"] == 5.01
    for day, close in [(days[1], 5.1), (days[2], 5.2), (days[4], 5.4), (days[5], 5.5)]:
        assert out.loc[day, "Source"] == LABEL and out.loc[day, "Close"] == close


def test_overlay_keeps_an_untraded_native_close_when_the_other_listing_did_not_trade_either():
    days = pd.bdate_range("2026-09-01", periods=4)
    converted = _rows(days, [5.0, 5.1, 5.2, 5.3], source=LABEL, volume=0.0)
    native = pd.concat(
        [
            _rows(days[:1], [5.0]),  # real: kept
            _rows(days[1:2], [5.09], volume=0.0),  # neither traded: native kept
            _rows(days[2:3], [float("nan")], volume=0.0),  # no close: filled even untraded
        ]
    )  # days[3] missing: filled even untraded

    out = overlay_alternate_listing(native, native.iloc[:0], converted, label="AIGE.L").set_index("Date")

    assert out["Source"].tolist() == ["Yahoo", "Yahoo", LABEL, LABEL]
    assert out["Close"].tolist() == [5.0, 5.09, 5.2, 5.3]


def test_overlay_keeps_an_untraded_native_close_the_other_listing_disagrees_with():
    """A stale print on the other venue (AIGE.MI, July 2012) must not replace a stored close."""
    days = pd.bdate_range("2026-09-01", periods=4)
    converted = _rows(days, [5.0, 5.05, 4.6, 5.0], source=LABEL, volume=50.0)
    native = pd.concat(
        [
            _rows(days[:1], [5.0]),
            _rows(days[1:3], [5.0, 5.0], volume=0.0),  # untraded: 1% off replaced, 8% off kept
            _rows(days[3:4], [5.0]),
        ]
    )

    out = overlay_alternate_listing(native, native.iloc[:0], converted, label="AIGE.L").set_index("Date")

    assert out["Source"].tolist() == ["Yahoo", LABEL, "Yahoo", "Yahoo"]
    assert out["Close"].tolist() == [5.0, 5.05, 5.0, 5.0]


def test_overlay_refuses_a_listing_on_another_basis(caplog):
    days = pd.bdate_range("2026-09-01", periods=4)
    native = _rows(days[:2], [5.0, 5.0])
    converted = _rows(days, [6.0, 6.0, 6.0, 6.0], source=LABEL)  # 20% off

    with caplog.at_level(logging.WARNING):
        out = overlay_alternate_listing(native, native.iloc[:0], converted, label="AIGE.L")

    assert out is native
    assert "do not match" in caplog.text


def test_overlay_checks_against_traded_rows_not_stooq():
    """0.7% apart on every date: fine against Yahoo, too far for Stooq's 0.5% per-date rule."""
    days = pd.bdate_range("2026-09-01", periods=4)
    stored = pd.concat([_rows(days[:2], [5.0, 5.0], source="Stooq"), _rows(days[2:3], [5.0])])
    converted = _rows(days, [5.035] * 4, source=LABEL)

    out = overlay_alternate_listing(stored.iloc[:0], stored, converted, label="AIGE.L")

    # Not refused; dates with a real native close (Stooq or Yahoo) stay native.
    assert out["Source"].tolist() == [LABEL]
    assert out["Date"].tolist() == [days[3]]


def test_overlay_falls_back_to_stored_converted_rows_for_continuity(caplog):
    days = pd.bdate_range("2026-09-01", periods=3)
    stored = _rows(days[:1], [5.0], source=LABEL)
    jumped = _rows(days, [7.0, 7.0, 7.0], source=LABEL)
    with caplog.at_level(logging.WARNING):
        out = overlay_alternate_listing(stored.iloc[:0], stored, jumped, label="AIGE.L")
    assert out.empty and "do not match" in caplog.text


def test_overlay_without_converted_rows_returns_native_unchanged():
    native = _rows(["2026-09-01"], [5.0])
    assert overlay_alternate_listing(native, native, native.iloc[:0], label="AIGE.L") is native


def test_compatible_rows_keeps_gap_only_alternate_rows():
    existing = _rows(pd.bdate_range("2026-09-01", periods=3), [5.0, 5.0, 5.0])
    gaps = pd.concat([_rows(["2026-09-07"], [5.1], source=LABEL), _rows(["2026-09-08"], [5.1], source="Stooq")])
    kept = compatible_rows(existing, gaps, label="AIGE.L")
    assert kept["Source"].tolist() == [LABEL]


# ── apply_price_source ────────────────────────────────────────


def test_apply_fetches_converts_and_labels(monkeypatch, caplog):
    days = pd.bdate_range("2026-09-01", periods=3)
    calls = _install_yahoo(monkeypatch, _yahoo_frame(days, [5.0, 5.1, 5.2], dividends=[0.0, 0.1, 0.0]))
    _install_fx(monkeypatch, {"EUR": {str(d.date()): 0.85 for d in days}, "USD": {str(d.date()): 0.75 for d in days}})
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: AIGE_META)
    monkeypatch.setattr(alternate_listing, "_stored_series", lambda *_a: pd.DataFrame(columns=STANDARD_COLUMNS))
    native = _rows(days[:1], [5.67])

    with caplog.at_level(logging.WARNING):
        out = apply_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert calls == ["AIGE.MI"]
    assert out["Source"].tolist() == ["Yahoo", LABEL, LABEL]
    assert set(out["Ticker"]) == {"AIGE.L"}
    assert out["Close"].tolist()[1:] == [float(f"{c * 0.85 / 0.75:.6g}") for c in (5.1, 5.2)]
    assert "Ignoring 1 dividends on alternate listing AIGE.MI" in caplog.text


def test_apply_refuses_a_listing_quoted_in_another_currency(monkeypatch, caplog):
    days = pd.bdate_range("2026-09-01", periods=2)
    _install_yahoo(monkeypatch, _yahoo_frame(days, [5.0, 5.1]), currency="USD")
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: AIGE_META)
    native = _rows(days[:1], [5.0])

    with caplog.at_level(logging.WARNING):
        out = apply_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert out is native
    assert "quoted in USD" in caplog.text


def test_apply_leaves_instruments_without_the_field_alone(monkeypatch):
    calls = _install_yahoo(monkeypatch, _yahoo_frame([], []))
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: {"currency": "GBP", "name": "x"})
    native = _rows(["2026-09-01"], [5.0])
    assert apply_price_source(native, "ABC", "L", date(2026, 9, 1), date(2026, 9, 1)) is native
    assert calls == []


def test_fetch_meta_timeseries_without_the_field_is_unchanged(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=5)
    native = _rows(days, [1.0] * 5, ticker="ABC.L")
    calls = _install_yahoo(monkeypatch, _yahoo_frame([], []))
    monkeypatch.setattr(fmt, "is_valid_ticker", lambda *_a: True)
    monkeypatch.setattr(fmt, "fetch_yahoo_timeseries_range", lambda *_a, **_k: native)
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: {"currency": "GBP", "name": "ABC"})

    out = fmt.fetch_meta_timeseries("ABC", "L", start_date=days[0].date(), end_date=days[-1].date())

    assert out is native
    assert calls == []


# ── fetch order: mode "primary" vs "fill_gaps" (#9712) ─────────

PRIMARY_META = {**AIGE_META, "price_source": {**AIGE_META["price_source"], "mode": MODE_PRIMARY}}
MI_CLOSE = 4.41  # 4.41 EUR * 0.85 / 0.75 = 4.998 USD


class NativeChain:
    """Records each native fetch window and returns the given rows inside it."""

    def __init__(self, rows: pd.DataFrame | None = None):
        self.rows = rows if rows is not None else _rows([], [])
        self.calls: list[tuple[date, date]] = []

    def __call__(self, start: date, end: date) -> pd.DataFrame:
        self.calls.append((start, end))
        days = pd.to_datetime(self.rows["Date"]).dt.date
        return self.rows.loc[((days >= start) & (days <= end)).to_numpy()].reset_index(drop=True)


def _install_listing(monkeypatch, meta, mi_days, *, fx_days=None, stored=None) -> list[str]:
    fx_days = mi_days if fx_days is None else fx_days
    calls = _install_yahoo(monkeypatch, _yahoo_frame(mi_days, [MI_CLOSE] * len(mi_days)))
    _install_fx(
        monkeypatch,
        {"EUR": {str(d.date()): 0.85 for d in fx_days}, "USD": {str(d.date()): 0.75 for d in fx_days}},
    )
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: meta)
    stored = pd.DataFrame(columns=STANDARD_COLUMNS) if stored is None else stored
    monkeypatch.setattr(alternate_listing, "_stored_series", lambda *_a: stored)
    return calls


def test_primary_makes_no_native_call_when_the_listing_covers_the_window(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=5)
    mi_calls = _install_listing(monkeypatch, PRIMARY_META, days)
    native = NativeChain(_rows(days, [5.0] * 5))

    out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert native.calls == []
    assert mi_calls == ["AIGE.MI"]
    assert out["Source"].tolist() == [LABEL] * 5
    assert out["Close"].tolist() == [float(f"{MI_CLOSE * 0.85 / 0.75:.6g}")] * 5


def test_primary_returns_the_same_rows_as_fill_gaps_when_native_has_nothing(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=5)
    stored = _rows(days[:2], [5.0, 5.0])  # stored native closes stay; neither mode returns them
    _install_listing(monkeypatch, AIGE_META, days, stored=stored)
    fill_gaps = fetch_with_price_source(NativeChain(), "AIGE", "L", days[0].date(), days[-1].date())
    _install_listing(monkeypatch, PRIMARY_META, days, stored=stored)
    primary = fetch_with_price_source(NativeChain(), "AIGE", "L", days[0].date(), days[-1].date())

    pd.testing.assert_frame_equal(primary.reset_index(drop=True), fill_gaps.reset_index(drop=True))
    assert pd.to_datetime(primary["Date"]).tolist() == list(days[2:])


def test_primary_fetches_native_only_over_uncovered_dates(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=6)
    # The listing has no row on days[2] or days[5].
    _install_listing(monkeypatch, PRIMARY_META, days.delete([2, 5]))
    native = NativeChain(_rows(days, [5.0, 5.0, 5.01, 5.0, 5.0, 5.02]))

    out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date()).set_index("Date")

    assert native.calls == [(days[2].date(), days[5].date())]
    assert list(out.index) == list(days)
    # Native rows are fetched for days[2..5]; the per-date rule keeps real ones.
    assert out["Source"].tolist() == [LABEL, LABEL, "Yahoo", "Yahoo", "Yahoo", "Yahoo"]
    assert out.loc[days[2], "Close"] == 5.01 and out.loc[days[5], "Close"] == 5.02


def test_primary_counts_stored_closes_as_covered(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=4)
    stored = _rows(days[3:], [5.0])
    _install_listing(monkeypatch, PRIMARY_META, days[:3], stored=stored)
    native = NativeChain()

    out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert native.calls == []
    assert pd.to_datetime(out["Date"]).tolist() == list(days[:3])


def test_primary_falls_back_to_the_whole_native_window_when_the_basis_is_refused(monkeypatch, caplog):
    days = pd.bdate_range("2026-09-01", periods=4)
    stored = _rows(days[:2], [6.0, 6.0])  # 20% off the converted listing
    _install_listing(monkeypatch, PRIMARY_META, days, stored=stored)
    native = NativeChain(_rows(days, [6.0] * 4))

    with caplog.at_level(logging.WARNING):
        out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert native.calls == [(days[0].date(), days[-1].date())]
    assert set(out["Source"]) == {"Yahoo"} and len(out) == 4
    assert "do not match" in caplog.text


def test_primary_falls_back_to_the_whole_native_window_when_the_listing_fails(monkeypatch, caplog):
    days = pd.bdate_range("2026-09-01", periods=3)
    _install_listing(monkeypatch, PRIMARY_META, days)
    _install_yahoo(monkeypatch, _yahoo_frame(days, [5.0] * 3), currency="USD")
    native = NativeChain(_rows(days, [5.0] * 3))

    with caplog.at_level(logging.WARNING):
        out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert native.calls == [(days[0].date(), days[-1].date())]
    assert set(out["Source"]) == {"Yahoo"}
    assert "quoted in USD" in caplog.text


def test_fill_gaps_fetches_native_for_the_whole_window_then_overlays(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=5)
    mi_calls = _install_listing(monkeypatch, AIGE_META, days)
    native_rows = _rows(days[:2], [5.0, 5.0])
    native = NativeChain(native_rows)

    out = fetch_with_price_source(native, "AIGE", "L", days[0].date(), days[-1].date())

    assert native.calls == [(days[0].date(), days[-1].date())]
    assert mi_calls == ["AIGE.MI"]
    expected = apply_price_source(native_rows, "AIGE", "L", days[0].date(), days[-1].date())
    pd.testing.assert_frame_equal(out.reset_index(drop=True), expected.reset_index(drop=True))
    assert out["Source"].tolist() == ["Yahoo", "Yahoo", LABEL, LABEL, LABEL]


def test_without_the_field_native_is_fetched_once_and_returned_as_is(monkeypatch):
    calls = _install_listing(monkeypatch, {"currency": "GBP", "name": "ABC"}, [])
    native = NativeChain(_rows(["2026-09-01"], [5.0]))
    out = fetch_with_price_source(native, "ABC", "L", date(2026, 9, 1), date(2026, 9, 1))
    assert native.calls == [(date(2026, 9, 1), date(2026, 9, 1))]
    assert out["Close"].tolist() == [5.0]
    assert calls == []


def _noisy_native_miss(_start, _end) -> pd.DataFrame:
    """What the native chain logs for AIGE.L: yfinance and Yahoo ERRORs, a Stooq cooldown WARNING."""
    logging.getLogger("yfinance").error("$AIGE.L: possibly delisted; no price data found")
    logging.getLogger("yahoo_timeseries").error("Failed to fetch Yahoo data for AIGE.L")
    logging.getLogger("stooq_timeseries").error("Failed to fetch Stooq data for AIGE.UK")
    logging.getLogger("stooq_timeseries").warning("Stooq request timed out; skipping Stooq during cooldown")
    logging.getLogger("backend.timeseries.fetch_ft_timeseries").warning("FT fetch failed for AIGE.L")
    return _rows([], [])


def _levels(caplog) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for record in caplog.records:
        out.setdefault(record.getMessage().split(" ")[0], []).append(record.levelno)
    return out


@pytest.mark.parametrize("meta", [AIGE_META, PRIMARY_META], ids=["fill_gaps", "primary"])
def test_native_misses_log_at_info_when_a_price_source_is_set(monkeypatch, caplog, meta):
    days = pd.bdate_range("2026-09-01", periods=3)
    _install_listing(monkeypatch, meta, days[:2])  # primary still needs native for days[2]

    with caplog.at_level(logging.INFO):
        fetch_with_price_source(_noisy_native_miss, "AIGE", "L", days[0].date(), days[-1].date())

    levels = _levels(caplog)
    assert levels["$AIGE.L:"] == [logging.INFO]
    assert levels["Failed"] == [logging.INFO, logging.INFO]
    assert levels["FT"] == [logging.INFO]
    # Stooq's cooldown affects every ticker, so it keeps its level.
    assert levels["Stooq"] == [logging.WARNING]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_native_misses_keep_their_level_without_a_price_source(monkeypatch, caplog):
    _install_listing(monkeypatch, {"currency": "GBP", "name": "ABC"}, [])

    with caplog.at_level(logging.INFO):
        fetch_with_price_source(_noisy_native_miss, "ABC", "L", date(2026, 9, 1), date(2026, 9, 1))
        logging.getLogger("yfinance").error("$XYZ.L: possibly delisted; outside the fetch")

    levels = _levels(caplog)
    assert levels["$AIGE.L:"] == [logging.ERROR]
    assert levels["Failed"] == [logging.ERROR, logging.ERROR]
    assert levels["$XYZ.L:"] == [logging.ERROR]


def test_fetch_meta_timeseries_in_primary_mode_skips_the_provider_chain(monkeypatch):
    days = pd.bdate_range("2026-09-01", periods=5)
    _install_listing(monkeypatch, PRIMARY_META, days)
    called: list[str] = []

    def provider(name):
        def fetch(*_a, **_k):
            called.append(name)
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        return fetch

    monkeypatch.setattr(fmt, "is_valid_ticker", lambda *_a: True)
    monkeypatch.setattr(fmt, "fetch_yahoo_timeseries_range", provider("yahoo"))
    monkeypatch.setattr(fmt, "fetch_stooq_timeseries_range", provider("stooq"))
    monkeypatch.setattr(fmt, "fetch_ft_df", provider("ft"))
    monkeypatch.setattr(fmt.config, "alpha_vantage_enabled", False, raising=False)

    out = fmt.fetch_meta_timeseries("AIGE", "L", start_date=days[0].date(), end_date=days[-1].date())

    assert called == []
    assert out["Source"].tolist() == [LABEL] * 5


# ── through the rolling cache ─────────────────────────────────


@pytest.fixture
def cache_base(monkeypatch, tmp_path):
    cache = importlib.import_module("backend.timeseries.cache")
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    return cache


def _write_fx(cache, currency: str, days, rate: float) -> None:
    path = cache._fx_cache_path(currency)
    cache._ensure_local_dir(path)
    pd.DataFrame({"Date": pd.to_datetime(days).astype("datetime64[ms]"), "Rate": rate}).to_parquet(path, index=False)


def test_refresh_fills_stored_gaps_from_the_alternate_listing(cache_base, monkeypatch):
    cache = cache_base
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 30)
    days = pd.bdate_range(end=pd.Timestamp(window_end), periods=10)
    _write_fx(cache, "EUR", days, 0.85)
    _write_fx(cache, "USD", days, 0.75)
    path = cache._cache_path("meta", "AIGE_L.parquet")
    stored = _rows(days[:8], [5.0] * 8)
    stored.loc[[2, 5], ["Open", "High", "Low", "Close"]] = float("nan")
    cache._save_parquet(stored, path)

    mi_close = 4.41  # 4.41 EUR * 0.85 / 0.75 = 4.998 USD, within 0.04% of the stored 5.0
    _install_yahoo(monkeypatch, _yahoo_frame(days, [mi_close] * 10))
    monkeypatch.setattr(alternate_listing, "get_instrument_meta", lambda _t: AIGE_META)
    monkeypatch.setattr(fmt, "is_valid_ticker", lambda *_a: True)
    monkeypatch.setattr(fmt, "fetch_yahoo_timeseries_range", lambda *_a, **_k: _rows(days[-1:], [5.02]))
    monkeypatch.setattr(fmt, "fetch_stooq_timeseries_range", lambda *_a, **_k: pd.DataFrame(columns=STANDARD_COLUMNS))
    monkeypatch.setattr(fmt, "fetch_ft_df", lambda *_a, **_k: pd.DataFrame(columns=STANDARD_COLUMNS))
    monkeypatch.setattr(fmt.config, "alpha_vantage_enabled", False, raising=False)

    cache._rolling_cache(
        # A 5-day window inside the stored range: the refresh extends it forward
        # and its 14-day overlap re-covers every stored date.
        fmt.fetch_meta_timeseries,
        path,
        {"ticker": "AIGE", "exchange": "L"},
        5,
        ticker="AIGE",
        exchange="L",
    )

    saved = cache._load_parquet(path).set_index("Date")
    converted = float(f"{mi_close * 0.85 / 0.75:.6g}")
    assert len(saved) == 10
    assert saved["Close"].notna().all()
    assert saved.loc[days[[2, 5, 8]], "Source"].tolist() == [LABEL] * 3
    assert saved.loc[days[[2, 5, 8]], "Close"].tolist() == [converted] * 3
    assert saved.loc[days[[0, 1, 3, 4, 6, 7]], "Close"].tolist() == [5.0] * 6
    assert saved.loc[days[9], "Source"] == "Yahoo" and saved.loc[days[9], "Close"] == 5.02
