"""Tests for the batch instrument helpers backing ``GET /instrument/batch``.

The partition property (§5.1 of docs/decisions/6911-client-side-eod-price-caching.md)
is the contract worth guarding: a ticker missing from all three buckets, or counted
in two, silently corrupts the caller's "no price history" tally rather than failing.
"""

import pandas as pd
import pytest

import backend.common.instrument_api as ia


def _stub_series(monkeypatch, *, resolvable, prices_by_ticker):
    """Wire batch_timeseries_for_tickers onto in-memory fixtures.

    *resolvable* is the set of tickers (upper-cased) that resolve to a
    (symbol, exchange) pair; *prices_by_ticker* maps upper-cased ticker to the
    price rows it should yield.
    """

    monkeypatch.setattr(
        ia,
        "_resolve_full_ticker",
        lambda ticker, latest: (("SYM", "L") if (ticker or "").upper() in resolvable else None),
    )

    def fake_timeseries(ticker, days=365, start_date=None, end_date=None):
        rows = prices_by_ticker.get((ticker or "").upper(), [])
        return {"prices": rows, "mini": {"7": rows[-7:], "30": rows[-30:], "180": rows[-180:]}}

    monkeypatch.setattr(ia, "timeseries_for_ticker", fake_timeseries)


ROW = {"date": "2026-05-16", "close": 97.5, "close_gbp": 97.5}


def test_batch_partitions_request_across_three_buckets(monkeypatch):
    _stub_series(
        monkeypatch,
        resolvable={"HAS.L", "NONE.L"},
        prices_by_ticker={"HAS.L": [ROW]},
    )

    res = ia.batch_timeseries_for_tickers(["HAS.L", "NONE.L", "BOGUS.L"])

    assert list(res["instruments"]) == ["HAS.L"]
    assert res["empty"] == ["NONE.L"]
    assert res["unknown"] == ["BOGUS.L"]

    # The partition property itself: union == request, no ticker in two buckets.
    buckets = list(res["instruments"]) + res["empty"] + res["unknown"]
    assert sorted(buckets) == sorted(["HAS.L", "NONE.L", "BOGUS.L"])
    assert len(buckets) == len(set(buckets))


def test_batch_distinguishes_empty_from_unknown(monkeypatch):
    """Resolvable-but-no-rows and unresolvable must not collapse together.

    The consolidated "no price history" notice is about the first case only.
    """
    _stub_series(monkeypatch, resolvable={"KNOWN.L"}, prices_by_ticker={})

    res = ia.batch_timeseries_for_tickers(["KNOWN.L", "TYPO.L"])

    assert res["empty"] == ["KNOWN.L"]
    assert res["unknown"] == ["TYPO.L"]


def test_batch_omits_mini_by_default(monkeypatch):
    _stub_series(monkeypatch, resolvable={"HAS.L"}, prices_by_ticker={"HAS.L": [ROW]})

    res = ia.batch_timeseries_for_tickers(["HAS.L"])

    assert res["instruments"]["HAS.L"] == {"prices": [ROW]}
    assert "mini" not in res["instruments"]["HAS.L"]


def test_batch_includes_mini_on_request(monkeypatch):
    _stub_series(monkeypatch, resolvable={"HAS.L"}, prices_by_ticker={"HAS.L": [ROW]})

    res = ia.batch_timeseries_for_tickers(["HAS.L"], include_mini=True)

    assert res["instruments"]["HAS.L"]["mini"]["7"] == [ROW]


def test_batch_dedupes_case_insensitively_keeping_caller_spelling(monkeypatch):
    """A caller keys its bookkeeping off the strings it sent, so echo those back."""
    _stub_series(monkeypatch, resolvable={"HAS.L"}, prices_by_ticker={"HAS.L": [ROW]})

    res = ia.batch_timeseries_for_tickers(["has.l", "HAS.L", "Has.L"])

    assert list(res["instruments"]) == ["has.l"]


def test_dedupe_tickers_drops_blanks_and_duplicates():
    assert ia.dedupe_tickers([" AAA.L ", "", "  ", "aaa.l", "BBB.L"]) == ["AAA.L", "BBB.L"]


def test_dedupe_tickers_on_empty_input():
    assert ia.dedupe_tickers([]) == []
    assert ia.dedupe_tickers(["", "   "]) == []


def test_batch_classifies_dotted_nonexistent_ticker_as_empty_not_unknown(monkeypatch):
    """Exercise the real ``_resolve_full_ticker``, not the stub every other test here uses.

    ``_resolve_full_ticker`` (see ``test_resolve_full_ticker_variants`` in
    test_instrument_api_functions.py) is structural, not existence-based: any
    ``SYMBOL.EX`` string splits into a ``(symbol, exchange)`` pair whether or
    not that instrument is real. Stubbing the resolver -- as ``_stub_series``
    does for every test above -- would hide a regression here, since it lets
    the test author decide which tickers are "unknown" rather than the real
    function. A dotted typo therefore lands in ``empty`` (resolves, no rows),
    never ``unknown``; only a bare symbol with no exchange suffix and no
    metadata match gets there. This backs the docstring/ADR claims directly.
    """
    monkeypatch.setattr(ia, "_TICKER_EXCHANGE_MAP", {})
    monkeypatch.setattr(ia, "_LATEST_PRICES", {})
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: None)

    res = ia.batch_timeseries_for_tickers(["BOGUS.L", "NOPE"])

    assert res["instruments"] == {}
    assert res["empty"] == ["BOGUS.L"]
    assert res["unknown"] == ["NOPE"]


def test_batch_applies_scaling_override(monkeypatch):
    """Prices from data/scaling_overrides.json must be scaled here too (#6985 review).

    batch_timeseries_for_tickers delegates to the real (unstubbed) timeseries_for_ticker
    for the actual price fetch -- _stub_series above replaces that function wholesale,
    which would hide this entirely, so this test drives the lower-level dependencies
    instead. timeseries_for_ticker is the shared helper behind both this batch endpoint
    and portfolio.py's instrument_detail; only the standalone /instrument route scaled
    independently, via its own hand-rolled dataframe pipeline. Without this fix, a batch
    response for e.g. GSK.L/LLOY.L would read up to 100x higher than /instrument for the
    same ticker. See also test_timeseries_for_ticker_applies_scaling_override in
    test_instrument_api_functions.py, which covers the same fix at the unit level.
    """
    df = pd.DataFrame({"date": ["2026-05-16"], "close": [97.5], "close_gbp": [97.5]})

    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, latest: ("HAS", "L"))
    monkeypatch.setattr(ia, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(ia, "load_meta_timeseries_range", lambda s, e, start_date, end_date: df)
    monkeypatch.setattr(ia, "get_scaling_override", lambda *args, **kwargs: 0.01)

    def _scale_close_only(df_in, scale):
        scaled = df_in.copy()
        scaled["close"] = scaled["close"] * scale
        return scaled

    monkeypatch.setattr(ia, "apply_scaling", _scale_close_only)

    res = ia.batch_timeseries_for_tickers(["HAS.L"])

    assert res["instruments"]["HAS.L"]["prices"][0]["close"] == pytest.approx(0.975)
    assert res["instruments"]["HAS.L"]["prices"][0]["close_gbp"] == pytest.approx(0.975)
