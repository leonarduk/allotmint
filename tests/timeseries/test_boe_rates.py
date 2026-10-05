"""Stored Bank of England rates (#9322): fetch -> normalise -> store -> load, no network."""

from datetime import date

import pandas as pd
import pytest

from backend.timeseries import boe_rates

CSV = """DATE,IUDBEDR,IUDSNPY,IUDMNPY,IUDLNPY
01 Jun 2007,5.5,5.5814,5.2873,4.9248
04 Jun 2007,5.5,5.5893,5.2896,4.93
05 Jun 2007,5.5,,,
"""


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(boe_rates._ts_cache, "_CACHE_BASE", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_fetch(monkeypatch):
    """Serve ``responses`` in order instead of calling the BoE; record each request."""
    calls = []
    responses = []

    def fetch(codes, start, end):
        calls.append((list(codes), start, end))
        return responses.pop(0)

    monkeypatch.setattr(boe_rates, "fetch_boe_csv", fetch)
    return calls, responses


def test_parse_drops_blank_days_per_series_and_adds_provenance():
    parsed = boe_rates.parse_boe_csv(CSV, ["IUDBEDR", "IUDMNPY"])

    bank = parsed["IUDBEDR"]
    assert bank["Date"].dt.date.tolist() == [date(2007, 6, 1), date(2007, 6, 4), date(2007, 6, 5)]
    assert bank["Value"].tolist() == [5.5, 5.5, 5.5]
    assert set(bank["Series"]) == {"IUDBEDR"}
    assert set(bank["Units"]) == {"percent"}
    assert set(bank["Source"]) == {"Bank of England IADB"}
    # The 10y yield had no value on 5 Jun, so it has no row there.
    assert parsed["IUDMNPY"]["Date"].dt.date.tolist() == [date(2007, 6, 1), date(2007, 6, 4)]
    assert list(bank.columns) == boe_rates.STORED_COLUMNS


@pytest.mark.parametrize("text", ["<html>Error</html>", "", "DATE,OTHER\n01 Jun 2007,1\n"])
def test_parse_rejects_responses_that_are_not_the_requested_csv(text):
    with pytest.raises(boe_rates.BoeFetchError):
        boe_rates.parse_boe_csv(text, ["IUDBEDR"])


def test_first_refresh_fetches_from_the_history_start_and_stores_one_file_per_series(store, fake_fetch):
    calls, responses = fake_fetch
    responses.append(CSV)

    added = boe_rates.refresh_boe_series(today=date(2007, 6, 5))

    assert calls == [(list(boe_rates.BOE_SERIES), boe_rates.BOE_HISTORY_START, date(2007, 6, 5))]
    assert added == {"IUDBEDR": 3, "IUDSNPY": 2, "IUDMNPY": 2, "IUDLNPY": 2}
    for code in boe_rates.BOE_SERIES:
        assert (store / "boe" / f"{code}.parquet").exists()
    stored = pd.read_parquet(store / "boe" / "IUDLNPY.parquet")
    assert list(stored.columns) == boe_rates.STORED_COLUMNS
    assert stored["Value"].tolist() == [4.9248, 4.93]


def test_refresh_appends_only_new_dates_from_the_earliest_series_end(store, fake_fetch):
    calls, responses = fake_fetch
    responses.append(CSV)
    boe_rates.refresh_boe_series(today=date(2007, 6, 5))
    # The yields stopped on 4 Jun, Bank Rate on 5 Jun: the next request starts
    # on 5 Jun, and Bank Rate ignores the 5 Jun row it already has.
    responses.append(
        "DATE,IUDBEDR,IUDSNPY,IUDMNPY,IUDLNPY\n05 Jun 2007,9.9,5.6,5.3,4.95\n06 Jun 2007,5.5,5.5,5.2,4.9\n"
    )

    added = boe_rates.refresh_boe_series(today=date(2007, 6, 6))

    assert calls[1][1] == date(2007, 6, 5)
    assert added == {"IUDBEDR": 1, "IUDSNPY": 2, "IUDMNPY": 2, "IUDLNPY": 2}
    bank = boe_rates.load_boe_series("IUDBEDR")
    assert bank["Value"].tolist() == [5.5, 5.5, 5.5, 5.5]
    assert bank["Date"].is_monotonic_increasing and not bank["Date"].duplicated().any()


def test_refresh_with_nothing_new_leaves_files_untouched(store, fake_fetch):
    calls, responses = fake_fetch
    responses.append(CSV)
    boe_rates.refresh_boe_series(["IUDBEDR"], today=date(2007, 6, 5))
    path = store / "boe" / "IUDBEDR.parquet"
    mtime = path.stat().st_mtime_ns

    assert boe_rates.refresh_boe_series(["IUDBEDR"], today=date(2007, 6, 5)) == {"IUDBEDR": 0}
    assert len(calls) == 1  # already up to date: no request at all
    responses.append("DATE,IUDBEDR\n")
    assert boe_rates.refresh_boe_series(["IUDBEDR"], today=date(2007, 6, 7)) == {"IUDBEDR": 0}
    assert path.stat().st_mtime_ns == mtime


def test_failed_fetch_raises_and_keeps_stored_data(store, fake_fetch):
    _calls, responses = fake_fetch
    responses.append(CSV)
    boe_rates.refresh_boe_series(["IUDBEDR"], today=date(2007, 6, 5))
    responses.append("<html>Service unavailable</html>")

    with pytest.raises(boe_rates.BoeFetchError):
        boe_rates.refresh_boe_series(["IUDBEDR"], today=date(2007, 6, 8))

    assert len(boe_rates.load_boe_series("IUDBEDR")) == 3


def test_load_filters_dates_and_never_fetches(store, monkeypatch, fake_fetch):
    _calls, responses = fake_fetch
    responses.append(CSV)
    boe_rates.refresh_boe_series(today=date(2007, 6, 5))
    monkeypatch.setattr(boe_rates, "fetch_boe_csv", lambda *_a: pytest.fail("loaders must not fetch"))

    window = boe_rates.load_boe_series("iudbedr", start=date(2007, 6, 4), end=date(2007, 6, 4))
    assert window["Date"].dt.date.tolist() == [date(2007, 6, 4)]

    wide = boe_rates.load_boe_rates(["IUDBEDR", "IUDMNPY"])
    assert list(wide.columns) == ["Date", "IUDBEDR", "IUDMNPY"]
    assert wide["IUDBEDR"].tolist() == [5.5, 5.5, 5.5]
    assert wide["IUDMNPY"].iloc[:2].tolist() == [5.2873, 5.2896]
    assert pd.isna(wide["IUDMNPY"].iloc[2])


def test_load_of_an_unrefreshed_series_is_empty(store):
    assert boe_rates.load_boe_series("IUDBEDR").empty
    assert boe_rates.load_boe_rates().empty


def test_unknown_series_codes_are_rejected(store):
    with pytest.raises(ValueError):
        boe_rates.load_boe_series("NOTACODE")
    with pytest.raises(ValueError):
        boe_rates.refresh_boe_series(["NOTACODE"])


def test_fetch_sends_a_browser_user_agent_and_iadb_params(monkeypatch):
    seen = {}

    class Resp:
        text = "DATE,IUDBEDR\n"

        def raise_for_status(self):
            return None

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return Resp()

    monkeypatch.setattr(boe_rates.requests, "get", fake_get)

    assert boe_rates.fetch_boe_csv(["IUDBEDR", "IUDLNPY"], date(2007, 6, 1), date(2026, 10, 2)) == "DATE,IUDBEDR\n"
    assert seen["url"] == boe_rates.BOE_IADB_CSV_URL
    assert seen["params"]["SeriesCodes"] == "IUDBEDR,IUDLNPY"
    assert seen["params"]["Datefrom"] == "01/Jun/2007"
    assert seen["params"]["Dateto"] == "02/Oct/2026"
    assert seen["params"]["UsingCodes"] == "Y"
    assert seen["headers"]["User-Agent"].startswith("Mozilla/5.0")
