"""Tests for backend.common.instrument_proxy (#9480): schema, validator and resolvers.

All prices, FX rates and metadata are synthetic and injected via monkeypatch;
nothing touches the network or the real data repo.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.common import instrument_proxy as ip
from backend.common import instruments
from backend.timeseries.cache import is_cache_only

VALID_PROXY = {
    "daily": [{"ticker": "IGLT.L", "weight": 1.0, "currency": "GBP", "scale": 1.0, "from": None, "to": None}],
    "long_history": [{"column": "uk_govt_bond_10y", "weight": 1.0}],
    "basis": "total_return",
    "rationale": "UK gilts 1-10y fund; IGLT is the closest stored series with history to 2007",
    "reviewed": "2026-10-05",
}


def _meta(proxy=None, **daily_override) -> dict:
    block = copy.deepcopy(VALID_PROXY) if proxy is None else proxy
    if daily_override:
        block["daily"][0].update(daily_override)
    return {"ticker": "GBPG.L", "currency": "GBP", "proxy": block}


@dataclass
class FakeData:
    prices: dict[str, pd.Series] = field(default_factory=dict)
    metas: dict[str, dict] = field(default_factory=dict)
    overrides: dict[str, float] = field(default_factory=dict)
    currencies: dict[str, str] = field(default_factory=dict)
    fx: dict[str, pd.DataFrame] = field(default_factory=dict)

    def add_prices(self, ticker: str, start: str, values) -> None:
        index = pd.bdate_range(start, periods=len(values))
        self.prices[ticker] = pd.Series(np.asarray(values, dtype=float), index=index)


@pytest.fixture
def data(monkeypatch) -> FakeData:
    fake = FakeData()

    def load_range(sym, exch, start, end):
        assert is_cache_only(), "proxy resolver must read the cache only"
        series = fake.prices.get(f"{sym}.{exch}")
        if series is None:
            return pd.DataFrame(columns=["Date", "Close"])
        series = series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
        return pd.DataFrame({"Date": series.index.astype("datetime64[ms]"), "Close": series.to_numpy()})

    def fx_history(curr, start=None, end=None):
        return fake.fx.get(curr, pd.DataFrame(columns=["Date", "Rate"]))

    monkeypatch.setattr(ip, "load_meta_timeseries_range", load_range)
    monkeypatch.setattr(ip, "get_scaling_override", lambda sym, exch, _req: fake.overrides.get(f"{sym}.{exch}", 1.0))
    monkeypatch.setattr(ip, "instrument_currency", lambda sym, exch: fake.currencies.get(f"{sym}.{exch}", "GBP"))
    monkeypatch.setattr(ip, "load_fx_history", fx_history)
    monkeypatch.setattr(ip, "get_instrument_meta", lambda t: fake.metas.get(t, {}))
    return fake


def _proxy_block(daily) -> dict:
    return {"daily": daily, "basis": "price", "rationale": "test proxy", "reviewed": "2026-10-05"}


# ──────────────────────────────────────────────────────────────
# parse_proxy / validate_proxy
# ──────────────────────────────────────────────────────────────
def test_valid_block_has_no_problems() -> None:
    assert ip.validate_proxy(_meta(), known_tickers={"IGLT.L"}, long_history_columns={"uk_govt_bond_10y"}) == []
    assert ip.validate_proxy(_meta()) == []


def test_missing_proxy_is_valid_and_parses_to_none() -> None:
    assert ip.validate_proxy({"ticker": "X.L"}) == []
    assert ip.validate_proxy(None) == []
    assert ip.parse_proxy({"ticker": "X.L"}) is None


def test_parse_proxy_types_and_defaults() -> None:
    meta = _meta()
    meta["proxy"]["daily"] = [{"ticker": "sega.l", "weight": 1, "to": "2009-01-01"}]
    proxy = ip.parse_proxy(meta)
    assert proxy is not None
    seg = proxy.daily[0]
    assert (seg.ticker, seg.weight, seg.currency, seg.scale) == ("SEGA.L", 1.0, None, 1.0)
    assert seg.window == (None, date(2009, 1, 1))
    assert proxy.long_history[0] == ip.LongHistoryComponent("uk_govt_bond_10y", 1.0)
    assert proxy.reviewed == date(2026, 10, 5)
    assert proxy.basis == "total_return"


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p["daily"][0].update(weight=0), "weight 0 is outside (0, 1]"),
        (lambda p: p["daily"][0].update(weight=1.5), "weight 1.5 is outside (0, 1]"),
        (lambda p: p["daily"][0].update(weight="1"), "weight must be a number"),
        (lambda p: p["daily"][0].update(weight=0.6), "weights sum to 0.6, expected 1"),
        (lambda p: p["daily"][0].update(scale=0), "scale must be a positive number"),
        (lambda p: p["daily"][0].update(currency="pounds"), "currency must be a currency code"),
        (lambda p: p["daily"][0].update(ticker="IGLT"), "must be SYMBOL.EXCHANGE"),
        (lambda p: p["daily"][0].update(ticker=None), "ticker is missing"),
        (lambda p: p["daily"][0].update(ticker="GBPG.L"), "is the instrument itself"),
        (lambda p: p["daily"][0].update({"from": "2009-13-01"}), "'from' is not an ISO date"),
        (lambda p: p["daily"][0].update({"from": "2010-01-01", "to": "2009-01-01"}), "is after 'to'"),
        (lambda p: p.update(daily="IGLT.L"), "proxy.daily must be a list"),
        (lambda p: p["daily"].append(5), "segment must be a JSON object"),
        (lambda p: p["long_history"][0].update(column="uk_property"), "unknown long-history column"),
        (lambda p: p["long_history"][0].update(weight=0.5), "proxy.long_history: weights sum to 0.5"),
        (lambda p: p.update(long_history={"uk_cash": 1}), "proxy.long_history must be a list"),
        (lambda p: p.update(basis="income"), "proxy.basis must be one of"),
        (lambda p: p.pop("rationale"), "proxy.rationale is required"),
        (lambda p: p.update(rationale="  "), "proxy.rationale is required"),
        (lambda p: p.pop("reviewed"), "proxy.reviewed is required"),
        (lambda p: p.update(reviewed="last week"), "'reviewed' is not an ISO date"),
        (lambda p: (p.pop("daily"), p.pop("long_history")), "at least one of 'daily' or 'long_history'"),
    ],
)
def test_each_rule_violation_has_a_specific_message(mutate, expected) -> None:
    meta = _meta()
    mutate(meta["proxy"])
    problems = ip.validate_proxy(meta)
    assert any(expected in p for p in problems), problems


def test_unknown_ticker_reported_against_known_series() -> None:
    problems = ip.validate_proxy(_meta(), known_tickers={"SLXX.L"})
    assert problems == ["proxy.daily[0]: unknown ticker IGLT.L (no stored series)"]


def test_overlapping_windows_and_duplicate_ticker_reported() -> None:
    daily = [
        {"ticker": "A.L", "weight": 1.0, "to": "2010-06-30"},
        {"ticker": "B.L", "weight": 0.5, "from": "2010-01-01"},
        {"ticker": "B.L", "weight": 0.5, "from": "2010-01-01"},
    ]
    problems = ip.validate_proxy({"ticker": "X.L", "proxy": _proxy_block(daily)})
    assert any("overlap" in p for p in problems), problems
    assert any("ticker B.L appears more than once" in p for p in problems), problems


def test_adjacent_windows_and_two_ticker_blend_are_valid() -> None:
    daily = [
        {"ticker": "A.L", "weight": 0.6, "to": "2008-12-31"},
        {"ticker": "B.L", "weight": 0.4, "to": "2008-12-31"},
        {"ticker": "A.L", "weight": 1.0, "from": "2009-01-01"},
    ]
    assert ip.validate_proxy({"ticker": "X.L", "proxy": _proxy_block(daily)}) == []


@pytest.mark.parametrize("bad", ["not a dict", 42, ["list"]])
def test_validate_never_raises_on_garbage(bad) -> None:
    assert ip.validate_proxy({"proxy": bad}) == ["proxy must be a JSON object"]
    assert ip.validate_proxy({"proxy": {"daily": [None, {"weight": float("nan")}], "long_history": [1]}})


# ──────────────────────────────────────────────────────────────
# proxied_daily_history
# ──────────────────────────────────────────────────────────────
def _returns(frame: pd.DataFrame) -> pd.Series:
    return frame["Close_gbp"].pct_change()


def test_no_proxy_returns_own_series_unchanged(data: FakeData) -> None:
    data.add_prices("OWN.L", "2020-01-01", [1000.0, 1010.0, 1020.0])
    data.overrides["OWN.L"] = 0.01  # pence line: scaled once, not twice
    out = ip.proxied_daily_history("OWN.L", date(2019, 1, 1), date(2020, 12, 31))
    assert list(out.columns) == ["Date", "Close_gbp", "Source"]
    assert out["Close_gbp"].tolist() == pytest.approx([10.0, 10.1, 10.2])
    assert set(out["Source"]) == {"own"}


def test_own_usd_series_converted_with_stored_fx(data: FakeData) -> None:
    data.add_prices("OWN.N", "2020-01-01", [100.0, 110.0])
    data.currencies["OWN.N"] = "USD"
    data.fx["USD"] = pd.DataFrame({"Date": pd.to_datetime(["2019-12-31"]), "Rate": [0.8]})
    out = ip.proxied_daily_history("OWN.N", date(2020, 1, 1), date(2020, 1, 31))
    assert out["Close_gbp"].tolist() == pytest.approx([80.0, 88.0])


def test_invalid_proxy_is_ignored_with_warning(data: FakeData, caplog) -> None:
    data.add_prices("OWN.L", "2015-01-01", [10.0, 11.0])
    data.add_prices("A.L", "2007-01-01", np.linspace(5, 9, 2100))
    data.metas["OWN.L"] = {"proxy": _proxy_block([{"ticker": "A.L", "weight": 0.5}])}
    with caplog.at_level(logging.WARNING, logger=ip.__name__):
        out = ip.proxied_daily_history("OWN.L", date(2007, 1, 1), date(2015, 12, 31))
    assert set(out["Source"]) == {"own"}
    assert "Ignoring invalid proxy for OWN.L" in caplog.text


def test_seamless_join_from_2007_for_instrument_starting_2015(data: FakeData) -> None:
    proxy_values = 100 * np.cumprod(1 + 0.0003 * np.sin(np.arange(2400)))
    data.add_prices("IGLT.L", "2007-01-01", proxy_values)
    data.add_prices("OWN.L", "2015-01-01", [50.0, 50.5, 51.0])
    data.metas["OWN.L"] = {"proxy": _proxy_block([{"ticker": "IGLT.L", "weight": 1.0}])}

    out = ip.proxied_daily_history("OWN.L", date(2007, 1, 1), date(2015, 12, 31))

    assert out["Date"].iloc[0] == pd.Timestamp("2007-01-01")
    before = out[out["Date"] < pd.Timestamp("2015-01-01")]
    after = out[out["Date"] >= pd.Timestamp("2015-01-01")]
    assert set(before["Source"]) == {"proxy:IGLT.L"}
    assert set(after["Source"]) == {"own"}
    assert after["Close_gbp"].iloc[0] == 50.0
    # Stitched returns equal the proxy's own returns up to the join: no level jump.
    proxy = data.prices["IGLT.L"]
    joined = out.set_index("Date")["Close_gbp"]
    expected = proxy.reindex(joined.index).ffill().pct_change()
    pre_join = joined.index <= pd.Timestamp("2015-01-01")
    assert joined.pct_change()[pre_join].iloc[1:].to_numpy() == pytest.approx(expected[pre_join].iloc[1:].to_numpy())


def test_two_ticker_blend_uses_weighted_returns(data: FakeData) -> None:
    data.add_prices("A.L", "2010-01-01", [100.0, 110.0, 99.0, 99.0, 99.0])
    data.add_prices("B.N", "2010-01-01", [10.0, 10.0, 10.5, 10.5, 10.5])
    data.currencies["B.N"] = "USD"
    data.fx["USD"] = pd.DataFrame({"Date": pd.to_datetime(["2009-01-01"]), "Rate": [0.5]})
    data.add_prices("OWN.L", "2010-01-07", [20.0, 21.0])  # starts on the 5th business day
    daily = [{"ticker": "A.L", "weight": 0.75}, {"ticker": "B.N", "weight": 0.25}]
    data.metas["OWN.L"] = {"proxy": _proxy_block(daily)}

    out = ip.proxied_daily_history("OWN.L", date(2010, 1, 1), date(2010, 1, 31))

    proxied = out[out["Source"] != "own"]
    assert set(proxied["Source"]) == {"proxy:A.L+B.N"}
    assert len(proxied) == 4
    expected = [0.75 * 0.10 + 0.25 * 0.0, 0.75 * -0.10 + 0.25 * 0.05, 0.0, 0.0]
    assert _returns(out).iloc[1:5].tolist() == pytest.approx(expected)
    assert out["Close_gbp"].iloc[4] == 20.0


def test_dated_eur_cents_to_gbp_switch_is_continuous(data: FakeData) -> None:
    # SEGA-style series: EUR cents up to 2009-01-01, GBP from 2009-01-02.
    dates = pd.bdate_range("2008-12-29", "2009-01-07")
    gbp_level = pd.Series(np.linspace(9.0, 9.9, len(dates)), index=dates)
    eur_cents = gbp_level / 0.9 * 100  # GBP = EUR cents * 0.01 * 0.9
    raw = eur_cents.where(dates <= pd.Timestamp("2009-01-01"), gbp_level)
    data.prices["SEGA.L"] = raw
    data.fx["EUR"] = pd.DataFrame({"Date": pd.to_datetime(["2008-01-01"]), "Rate": [0.9]})
    data.add_prices("OWN.L", "2009-01-08", [99.0, 100.0])
    daily = [
        {"ticker": "SEGA.L", "weight": 1.0, "currency": "EUR", "scale": 0.01, "to": "2009-01-01"},
        {"ticker": "SEGA.L", "weight": 1.0, "currency": "GBP", "from": "2009-01-02"},
    ]
    data.metas["OWN.L"] = {"proxy": _proxy_block(daily)}

    out = ip.proxied_daily_history("OWN.L", date(2008, 12, 1), date(2009, 1, 31)).set_index("Date")

    proxied = out[out["Source"] != "own"]["Close_gbp"]
    assert proxied.index[0] == pd.Timestamp("2008-12-29")
    # A continuous GBP series: every step equals the true GBP level's step,
    # including across 2009-01-01 -> 2009-01-02 (no 100x or FX jump).
    expected = gbp_level.pct_change().iloc[1:]
    assert proxied.pct_change().iloc[1:].to_numpy() == pytest.approx(expected.to_numpy())
    assert set(out["Source"].iloc[:-2]) == {"proxy:SEGA.L"}


def test_consecutive_windows_with_different_tickers_chain_returns(data: FakeData) -> None:
    # Global-fund pattern (allotmint-data#35): BUT.L to 2009-01-01, then IWRD.L,
    # both GBX lines with a 0.01 override and currency "GBP". Their levels differ
    # ~20x, so splicing by price would jump; chaining returns must not.
    dates = pd.bdate_range("2008-12-24", "2009-01-07")
    but = pd.Series(np.linspace(50000.0, 51200.0, len(dates)), index=dates)
    iwrd = pd.Series(2500.0 * (1 + 0.01 * np.cos(np.arange(len(dates)))), index=dates)
    data.prices.update({"BUT.L": but, "IWRD.L": iwrd})
    data.overrides.update({"BUT.L": 0.01, "IWRD.L": 0.01})
    data.currencies.update({"BUT.L": "GBX", "IWRD.L": "GBX"})
    data.add_prices("VHYL.L", "2009-01-08", [40.0, 40.4])
    daily = [
        {"ticker": "BUT.L", "weight": 1.0, "currency": "GBP", "scale": 1.0, "from": None, "to": "2009-01-01"},
        {"ticker": "IWRD.L", "weight": 1.0, "currency": "GBP", "scale": 1.0, "from": "2009-01-02", "to": None},
    ]
    data.metas["VHYL.L"] = {"proxy": _proxy_block(daily)}

    out = ip.proxied_daily_history("VHYL.L", date(2008, 12, 1), date(2009, 1, 31)).set_index("Date")

    boundary = pd.Timestamp("2009-01-02")
    expected_returns = pd.concat([but.pct_change()[but.index < boundary], iwrd.pct_change()[iwrd.index >= boundary]])
    proxied = out[out["Source"] != "own"]
    assert proxied.index[0] == pd.Timestamp("2008-12-24")
    assert proxied.loc[: pd.Timestamp("2009-01-01"), "Source"].eq("proxy:BUT.L").all()
    assert proxied.loc[boundary:, "Source"].eq("proxy:IWRD.L").all()
    # Every step, including the boundary day (IWRD's own 01-01 close -> 01-02), is the proxy's return.
    stitched = out["Close_gbp"].pct_change()
    assert stitched.loc[: pd.Timestamp("2009-01-07")].iloc[1:].to_numpy() == pytest.approx(
        expected_returns.iloc[1:].to_numpy()
    )
    assert stitched.loc[boundary] == pytest.approx(iwrd.loc[boundary] / iwrd.loc[pd.Timestamp("2009-01-01")] - 1)
    assert out.loc[pd.Timestamp("2009-01-08"), "Close_gbp"] == 40.0


def test_gbx_proxy_is_not_double_scaled(data: FakeData) -> None:
    # The override already turns pence into pounds; the default currency
    # (GBX from metadata) must then count as GBP, not divide by 100 again.
    data.add_prices("PX.L", "2012-01-02", [1000.0, 1100.0, 1100.0])
    data.overrides["PX.L"] = 0.01
    data.currencies["PX.L"] = "GBX"
    data.add_prices("OWN.L", "2012-01-04", [11.0])
    data.metas["OWN.L"] = {"proxy": _proxy_block([{"ticker": "PX.L", "weight": 1.0}])}
    out = ip.proxied_daily_history("OWN.L", date(2012, 1, 1), date(2012, 1, 31))
    assert out["Close_gbp"].tolist() == pytest.approx([10.0, 11.0, 11.0])


def test_explicit_pence_currency_and_missing_fx(data: FakeData, caplog) -> None:
    # An explicit GBX segment means the scaled close is in pence: x0.01 once.
    data.add_prices("PX.L", "2012-01-02", [500.0, 600.0])
    data.add_prices("OWN.L", "2012-01-03", [6.0])
    data.metas["OWN.L"] = {"proxy": _proxy_block([{"ticker": "PX.L", "weight": 1.0, "currency": "GBX"}])}
    out = ip.proxied_daily_history("OWN.L", date(2012, 1, 1), date(2012, 1, 31))
    assert out["Close_gbp"].tolist() == pytest.approx([5.0, 6.0])

    # A currency with no stored FX gives no proxy rows, not a crash.
    data.metas["OWN.L"] = {"proxy": _proxy_block([{"ticker": "PX.L", "weight": 1.0, "currency": "JPY"}])}
    with caplog.at_level(logging.WARNING, logger=ip.__name__):
        out = ip.proxied_daily_history("OWN.L", date(2012, 1, 1), date(2012, 1, 31))
    assert set(out["Source"]) == {"own"}
    assert "No stored JPY FX history" in caplog.text


def test_segment_from_date_bounds_the_proxy(data: FakeData) -> None:
    data.add_prices("A.L", "2011-01-03", [1.0] * 10)
    data.add_prices("OWN.L", "2011-01-17", [5.0])
    daily = [{"ticker": "A.L", "weight": 1.0, "from": "2011-01-10"}]
    data.metas["OWN.L"] = {"proxy": _proxy_block(daily)}
    out = ip.proxied_daily_history("OWN.L", date(2011, 1, 1), date(2011, 1, 31))
    assert out["Date"].iloc[0] == pd.Timestamp("2011-01-10")


def test_no_own_history_returns_empty_with_warning(data: FakeData, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger=ip.__name__):
        out = ip.proxied_daily_history("NONE.L", date(2011, 1, 1), date(2011, 1, 31))
    assert out.empty and list(out.columns) == ["Date", "Close_gbp", "Source"]
    assert "No own price history for NONE.L" in caplog.text


# ──────────────────────────────────────────────────────────────
# long_history_annual
# ──────────────────────────────────────────────────────────────
def _write_long_history(root) -> None:
    folder = root / "timeseries" / "long_history"
    folder.mkdir(parents=True)
    (folder / "annual_returns_gbp.csv").write_text(
        "year,uk_cpi_inflation,gbp_per_usd,uk_cash,uk_govt_bond_10y,uk_equity,gold_gbp\n"
        "1927,0.01,0.2,0.04,0.05,0.10,\n"
        "1928,0.01,0.2,0.04,0.06,0.20,0.30\n"
        "1929,0.01,0.2,0.05,-0.02,-0.10,0.00\n",
        encoding="utf-8",
    )


def test_long_history_weighting(data: FakeData, monkeypatch, tmp_path) -> None:
    _write_long_history(tmp_path)
    monkeypatch.setattr(ip.config, "data_root", tmp_path)
    block = _proxy_block(None)
    block.pop("daily")
    block["long_history"] = [{"column": "uk_equity", "weight": 0.6}, {"column": "gold_gbp", "weight": 0.4}]
    data.metas["MIX.L"] = {"proxy": block}

    out = ip.long_history_annual("MIX.L")

    # 1927 has no gold, so it is dropped rather than silently reweighted.
    assert out.index.tolist() == [1928, 1929]
    assert out.tolist() == pytest.approx([0.6 * 0.20 + 0.4 * 0.30, 0.6 * -0.10])


def test_long_history_missing_csv_is_empty_with_message(data: FakeData, monkeypatch, tmp_path, caplog) -> None:
    monkeypatch.setattr(ip.config, "data_root", tmp_path)
    data.metas["GBPG.L"] = _meta()
    with caplog.at_level(logging.WARNING, logger=ip.__name__):
        out = ip.long_history_annual("GBPG.L")
    assert out.empty
    assert "Long-history returns CSV not found" in caplog.text


def test_long_history_csv_missing_column_is_empty(data: FakeData, monkeypatch, tmp_path, caplog) -> None:
    _write_long_history(tmp_path)
    monkeypatch.setattr(ip.config, "data_root", tmp_path)
    block = _proxy_block(None)
    block.pop("daily")
    block["long_history"] = [{"column": "us_equity_gbp", "weight": 1.0}]
    data.metas["US.L"] = {"proxy": block}
    with caplog.at_level(logging.WARNING, logger=ip.__name__):
        assert ip.long_history_annual("US.L").empty
    assert "lacks columns ['us_equity_gbp']" in caplog.text


def test_long_history_without_mapping_is_empty(data: FakeData) -> None:
    assert ip.long_history_annual("PLAIN.L").empty


# ──────────────────────────────────────────────────────────────
# Metadata round trip
# ──────────────────────────────────────────────────────────────
def test_instrument_meta_keeps_proxy_block(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.setattr(instruments.config, "data_root", tmp_path)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    instruments.get_instrument_meta.cache_clear()
    meta = _meta()

    path = instruments.save_instrument_meta("GBPG", "L", meta)

    assert json.loads(path.read_text(encoding="utf-8"))["proxy"] == VALID_PROXY
    loaded = instruments.get_instrument_meta("GBPG.L")
    assert loaded["proxy"] == VALID_PROXY
    assert ip.validate_proxy(loaded) == []
    instruments.get_instrument_meta.cache_clear()
