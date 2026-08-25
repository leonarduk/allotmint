"""Tests for the batch instrument helpers backing ``GET /instrument/batch``.

The partition property (§5.1 of docs/decisions/6911-client-side-eod-price-caching.md)
is the contract worth guarding: a ticker missing from all three buckets, or counted
in two, silently corrupts the caller's "no price history" tally rather than failing.
"""

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
