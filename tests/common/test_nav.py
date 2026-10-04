"""NAV providers and premium/discount (backend/common/nav.py). No network: prices and FX are injected."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from backend.common import nav
from backend.common.nav import CsvNavProvider, MetadataNavProvider, NavRecord, load_nav_csv, nav_discount, nav_to_gbp

TRUST_META = {"ticker": "3IN.L", "instrument_type": "Investment Trust", "currency": "GBX"}
HEADER = "ticker,nav,currency,nav_date,source\n"


class FixedProvider:
    name = "fixed"

    def __init__(self, record):
        self.record = record

    def latest_nav(self, ticker):
        return self.record


def _meta(monkeypatch, meta):
    monkeypatch.setattr(nav, "get_instrument_meta", lambda ticker: dict(meta))


def _price(value, on=date(2026, 9, 30)):
    calls = []

    def lookup(symbol, exchange, when):
        calls.append((symbol, exchange, when))
        return value, on

    lookup.calls = calls
    return lookup


def _no_fx(currency):
    raise AssertionError(f"FX should not be needed for {currency}")


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "navs.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


# ───────────────────────────── CSV store ─────────────────────────────


def test_load_nav_csv_keeps_the_latest_dated_row_per_ticker(tmp_path):
    path = _write(
        tmp_path,
        "3in.l,370.0,GBX,2026-08-31,RNS\n" "3IN.L,380.5,GBX,2026-09-30,RNS\n" "3IN.L,999,GBX,,undated\n",
    )
    navs = load_nav_csv(path)
    assert navs["3IN.L"] == NavRecord(nav=380.5, currency="GBX", nav_date=date(2026, 9, 30), source="RNS")


def test_load_nav_csv_drops_rows_without_a_currency_or_a_positive_nav(tmp_path, caplog):
    path = _write(tmp_path, "HICL.L,160.2,,2026-09-30,RNS\nUKW.L,-1,GBX,2026-09-30,RNS\nNESF.L,abc,GBX,,\n")
    assert load_nav_csv(path) == {}
    assert "explicit currency" in caplog.text


def test_load_nav_csv_missing_file_is_empty(tmp_path):
    assert load_nav_csv(tmp_path / "absent.csv") == {}


def test_csv_provider_rereads_an_edited_file(tmp_path):
    path = _write(tmp_path, "3IN.L,380.5,GBX,2026-09-30,RNS\n")
    provider = CsvNavProvider(lambda: (path,), bucket_factory=lambda: None)
    assert provider.latest_nav("3in.l").nav == 380.5

    path.write_text(HEADER + "3IN.L,390.0,GBX,2026-10-01,RNS\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert provider.latest_nav("3IN.L").nav == 390.0


def test_metadata_provider_needs_an_explicit_nav_currency(monkeypatch):
    _meta(monkeypatch, {"nav_per_share": 3.805, "nav_currency": "GBP", "nav_as_of": "2026-09-30"})
    assert MetadataNavProvider().latest_nav("3IN.L") == NavRecord(3.805, "GBP", date(2026, 9, 30), "metadata")

    _meta(monkeypatch, {"nav_per_share": 3.805})
    assert MetadataNavProvider().latest_nav("3IN.L") is None


def test_latest_nav_prefers_the_newer_date_and_the_first_provider_on_a_tie():
    older = NavRecord(370.0, "GBX", date(2026, 8, 31), "metadata")
    newer = NavRecord(380.5, "GBX", date(2026, 9, 30), "RNS")
    same_day = NavRecord(3.805, "GBP", date(2026, 9, 30), "other")
    undated = NavRecord(1.0, "GBP", None, "metadata")

    assert nav.latest_nav("X", [FixedProvider(older), FixedProvider(newer)]) is newer
    assert nav.latest_nav("X", [FixedProvider(newer), FixedProvider(same_day)]) is newer
    assert nav.latest_nav("X", [FixedProvider(undated), FixedProvider(older)]) is older
    assert nav.latest_nav("X", [FixedProvider(older), FixedProvider(undated)]) is older


# ───────────────────────────── units ─────────────────────────────


@pytest.mark.parametrize(
    "value, currency, expected",
    [(380.5, "GBX", 3.805), (380.5, "GBp", 3.805), (3.805, "GBP", 3.805)],
)
def test_nav_to_gbp_scales_pence_exactly_without_fx(value, currency, expected):
    gbp, fx = nav_to_gbp(value, currency, _no_fx)
    assert gbp == pytest.approx(expected)
    assert fx is False


def test_nav_to_gbp_uses_the_cached_fx_rate_and_flags_it():
    assert nav_to_gbp(1.0, "EUR", lambda ccy: 0.85) == (pytest.approx(0.85), True)
    assert nav_to_gbp(1.0, "EUR", lambda ccy: None) == (None, False)


# ───────────────────────────── discount ─────────────────────────────


def test_non_closed_end_instruments_get_no_nav(monkeypatch):
    _meta(monkeypatch, {"instrumentType": "ETF"})
    result = nav_discount("VWRL.L", providers=[], price_lookup=_price(1.0))
    assert result.applicable is False
    assert result.nav is None and result.premium_discount is None
    assert "closed-end" in result.reason


def test_closed_end_type_is_read_from_either_metadata_key(monkeypatch):
    _meta(monkeypatch, {"instrumentType": "investment trust"})
    assert nav_discount("3IN.L", providers=[]).applicable is True


def test_closed_end_fund_without_a_nav_says_where_to_add_one(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    result = nav_discount("3IN.L", providers=[FixedProvider(None)], price_lookup=_price(3.5))
    assert result.applicable is True
    assert result.premium_discount is None
    assert "navs.csv" in result.reason


def test_discount_uses_the_close_on_the_nav_date(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    lookup = _price(3.425, on=date(2026, 9, 30))
    record = NavRecord(380.5, "GBX", date(2026, 9, 30), "RNS")

    result = nav_discount("3in.l", providers=[FixedProvider(record)], price_lookup=lookup, fx_lookup=_no_fx)

    assert lookup.calls == [("3IN", "L", date(2026, 9, 30))]
    assert result.nav_gbp == pytest.approx(3.805)
    assert result.price_gbp == 3.425
    assert result.price_date == "2026-09-30"
    assert result.nav_date == "2026-09-30"
    assert result.premium_discount == pytest.approx(-0.0999, abs=1e-4)
    assert result.premium_discount_pct == pytest.approx(-9.99, abs=0.01)
    assert result.reason is None and result.warnings == []


def test_pence_and_pound_navs_give_the_same_premium(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    pence = NavRecord(380.5, "GBX", date(2026, 9, 30), "RNS")
    pounds = NavRecord(3.805, "GBP", date(2026, 9, 30), "RNS")
    a = nav_discount("3IN.L", providers=[FixedProvider(pence)], price_lookup=_price(4.0))
    b = nav_discount("3IN.L", providers=[FixedProvider(pounds)], price_lookup=_price(4.0))
    assert a.premium_discount == b.premium_discount == pytest.approx(0.0512, abs=1e-4)


def test_a_units_mix_up_is_reported_not_shown_as_a_number(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    # A pence NAV mislabelled as GBP: price 3.425 GBP vs "NAV" 380.5 GBP.
    record = NavRecord(380.5, "GBP", date(2026, 9, 30), "RNS")
    result = nav_discount("3IN.L", providers=[FixedProvider(record)], price_lookup=_price(3.425))
    assert result.premium_discount is None and result.premium_discount_pct is None
    assert "implausible" in result.reason


def test_missing_price_is_explained(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    record = NavRecord(380.5, "GBX", date(2026, 9, 30), "RNS")
    result = nav_discount("3IN.L", providers=[FixedProvider(record)], price_lookup=_price(None, on=None))
    assert result.nav_gbp == pytest.approx(3.805)
    assert result.premium_discount is None
    assert "No cached price" in result.reason


def test_foreign_currency_nav_is_converted_and_flagged(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    record = NavRecord(1.0, "EUR", date(2026, 9, 30), "RNS")
    result = nav_discount(
        "SERE.L", providers=[FixedProvider(record)], price_lookup=_price(0.6), fx_lookup=lambda ccy: 0.85
    )
    assert result.fx_converted is True
    assert result.premium_discount == pytest.approx(0.6 / 0.85 - 1, abs=1e-4)
    assert any("FX" in warning for warning in result.warnings)


def test_foreign_currency_nav_without_a_cached_rate_is_explained(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    record = NavRecord(1.0, "EUR", date(2026, 9, 30), "RNS")
    result = nav_discount(
        "SERE.L", providers=[FixedProvider(record)], price_lookup=_price(0.6), fx_lookup=lambda c: None
    )
    assert result.premium_discount is None
    assert "FX" in result.reason


def test_undated_nav_is_compared_with_the_latest_close_and_warned(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    lookup = _price(3.425, on=date(2026, 10, 2))
    record = NavRecord(380.5, "GBX", None, "metadata")
    result = nav_discount("3IN.L", providers=[FixedProvider(record)], price_lookup=lookup, today=date(2026, 10, 3))
    assert lookup.calls == [("3IN", "L", date(2026, 10, 3))]
    assert result.nav_date is None
    assert any("no date" in warning for warning in result.warnings)


def test_default_price_lookup_reads_the_cache_only(monkeypatch):
    from backend.common import holding_utils
    from backend.timeseries.cache import is_cache_only

    seen = {}

    def fake_dated_price(symbol, exchange, when):
        seen["cache_only"] = is_cache_only()
        seen["args"] = (symbol, exchange, when)
        return 3.425, "cache", date(2026, 9, 29)

    monkeypatch.setattr(holding_utils, "_get_dated_price_for_date_scaled", fake_dated_price)
    assert nav.default_price_lookup("3IN", "L", date(2026, 9, 30)) == (3.425, date(2026, 9, 29))
    assert seen == {"cache_only": True, "args": ("3IN", "L", date(2026, 9, 30))}


def test_as_dict_is_json_ready(monkeypatch):
    _meta(monkeypatch, {"instrument_type": "ETF"})
    payload = nav_discount("VWRL.L", providers=[]).as_dict()
    assert payload["ticker"] == "VWRL.L"
    assert payload["applicable"] is False
    assert payload["warnings"] == []


def test_foreign_nav_without_a_rate_is_not_reported_as_converted(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    record = NavRecord(1.0, "EUR", date(2026, 9, 30), "RNS")
    result = nav_discount(
        "SERE.L", providers=[FixedProvider(record)], price_lookup=_price(0.6), fx_lookup=lambda c: None
    )
    assert result.fx_converted is False
    assert result.warnings == []


def test_a_ticker_without_an_exchange_suffix_is_rejected(monkeypatch):
    _meta(monkeypatch, TRUST_META)
    lookup = _price(3.425)
    result = nav_discount("3IN", providers=[], price_lookup=lookup)
    assert result.applicable is False
    assert "exchange suffix" in result.reason
    assert lookup.calls == []


def test_load_nav_csv_rejects_a_file_with_the_wrong_header(tmp_path, caplog):
    path = tmp_path / "navs.csv"
    path.write_text("symbol,value\n3IN.L,380.5\n", encoding="utf-8")
    assert load_nav_csv(path) == {}
    assert "missing column" in caplog.text
