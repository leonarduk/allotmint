"""Stored FRED credit spreads (#10602): fetch -> normalise -> store -> load, no network."""

from datetime import date

import pandas as pd
import pytest
import requests

from backend.timeseries import fred_series

BAA_CSV = """observation_date,BAA10Y
1986-01-02,1.85
1986-01-03,.
1986-01-06,1.80
1986-01-07,
"""


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(fred_series._ts_cache, "_CACHE_BASE", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_fetch(monkeypatch):
    """Serve ``responses[code]`` in order instead of calling FRED; record each request."""
    calls = []
    responses: dict[str, list] = {}

    def fetch(code, start=None):
        calls.append((code, start))
        response = responses[code].pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(fred_series, "fetch_fred_csv", fetch)
    return calls, responses


def _csv(code: str, rows: list[tuple[str, str]]) -> str:
    return f"observation_date,{code}\n" + "".join(f"{d},{v}\n" for d, v in rows)


def test_parse_drops_dot_and_blank_cells_and_adds_provenance():
    parsed = fred_series.parse_fred_csv(BAA_CSV, "BAA10Y")

    assert parsed["Date"].dt.date.tolist() == [date(1986, 1, 2), date(1986, 1, 6)]
    assert parsed["Value"].tolist() == [1.85, 1.80]
    assert set(parsed["Series"]) == {"BAA10Y"}
    assert set(parsed["Units"]) == {"percent"}
    assert set(parsed["Source"]) == {"FRED"}
    assert list(parsed.columns) == fred_series.STORED_COLUMNS


def test_parse_accepts_the_older_date_header():
    parsed = fred_series.parse_fred_csv("DATE,AAA10Y\n1983-01-03,1.2\n", "AAA10Y")
    assert parsed["Value"].tolist() == [1.2]


@pytest.mark.parametrize("text", ["<html>Error</html>", "", "observation_date,OTHER\n1986-01-02,1\n"])
def test_parse_rejects_responses_that_are_not_the_requested_csv(text):
    with pytest.raises(fred_series.FredFetchError):
        fred_series.parse_fred_csv(text, "BAA10Y")


def test_first_refresh_fetches_full_history_and_stores_one_file_per_series(store, fake_fetch):
    calls, responses = fake_fetch
    for code in fred_series.FRED_SERIES:
        responses[code] = [_csv(code, [("2024-01-02", "3.1"), ("2024-01-03", "3.2")])]
    responses["BAA10Y"] = [BAA_CSV]

    added = fred_series.refresh_fred_series(today=date(2024, 1, 3))

    assert calls == [(code, None) for code in fred_series.FRED_SERIES]
    assert added == {"BAA10Y": 2, "AAA10Y": 2, "BAMLH0A0HYM2": 2, "BAMLC0A0CM": 2, "BAMLHE00EHYIOAS": 2}
    for code in fred_series.FRED_SERIES:
        assert (store / "fred" / f"{code}.parquet").exists()
    stored = pd.read_parquet(store / "fred" / "BAA10Y.parquet")
    assert list(stored.columns) == fred_series.STORED_COLUMNS
    assert stored["Value"].tolist() == [1.85, 1.80]


def test_refresh_appends_only_dates_after_the_last_stored_one(store, fake_fetch):
    calls, responses = fake_fetch
    responses["BAA10Y"] = [
        BAA_CSV,
        # FRED may repeat the start day; a changed value there must not rewrite the stored row.
        _csv("BAA10Y", [("1986-01-06", "9.99"), ("1986-01-07", "1.75"), ("1986-01-08", ".")]),
    ]
    fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 7))

    added = fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 8))

    assert calls[1] == ("BAA10Y", date(1986, 1, 7))
    assert added == {"BAA10Y": 1}
    stored = fred_series.load_fred_series("BAA10Y")
    assert stored["Value"].tolist() == [1.85, 1.80, 1.75]
    assert stored["Date"].is_monotonic_increasing and not stored["Date"].duplicated().any()


def test_refresh_with_nothing_new_leaves_files_untouched(store, fake_fetch):
    calls, responses = fake_fetch
    responses["BAA10Y"] = [BAA_CSV, "observation_date,BAA10Y\n"]
    fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 6))
    path = store / "fred" / "BAA10Y.parquet"
    mtime = path.stat().st_mtime_ns

    assert fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 6)) == {"BAA10Y": 0}
    assert len(calls) == 1  # already up to date: no request at all
    assert fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 9)) == {"BAA10Y": 0}
    assert path.stat().st_mtime_ns == mtime


def test_one_failed_series_keeps_its_data_and_the_others_still_refresh(store, fake_fetch):
    _calls, responses = fake_fetch
    responses["BAA10Y"] = [BAA_CSV, requests.ConnectionError("FRED down")]
    responses["AAA10Y"] = [_csv("AAA10Y", [("1986-01-02", "0.9")]), _csv("AAA10Y", [("1986-01-07", "0.8")])]
    fred_series.refresh_fred_series(["BAA10Y", "AAA10Y"], today=date(1986, 1, 6))

    added = fred_series.refresh_fred_series(["BAA10Y", "AAA10Y"], today=date(1986, 1, 8))

    assert added == {"AAA10Y": 1}
    assert len(fred_series.load_fred_series("BAA10Y")) == 2


def test_refresh_raises_when_every_series_fails_and_keeps_stored_data(store, fake_fetch):
    _calls, responses = fake_fetch
    responses["BAA10Y"] = [BAA_CSV, "<html>Service unavailable</html>"]
    fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 6))

    with pytest.raises(fred_series.FredFetchError):
        fred_series.refresh_fred_series(["BAA10Y"], today=date(1986, 1, 9))

    assert len(fred_series.load_fred_series("BAA10Y")) == 2


def test_load_filters_dates_and_never_fetches(store, monkeypatch, fake_fetch):
    _calls, responses = fake_fetch
    responses["BAA10Y"] = [BAA_CSV]
    responses["AAA10Y"] = [_csv("AAA10Y", [("1986-01-02", "0.9"), ("1986-01-03", "0.95")])]
    fred_series.refresh_fred_series(["BAA10Y", "AAA10Y"], today=date(1986, 1, 6))
    monkeypatch.setattr(fred_series, "fetch_fred_csv", lambda *_a, **_k: pytest.fail("loaders must not fetch"))

    window = fred_series.load_fred_series("baa10y", start=date(1986, 1, 6), end=date(1986, 1, 6))
    assert window["Value"].tolist() == [1.80]

    wide = fred_series.load_fred_rates(["BAA10Y", "AAA10Y"])
    assert list(wide.columns) == ["Date", "BAA10Y", "AAA10Y"]
    assert wide["Date"].dt.date.tolist() == [date(1986, 1, 2), date(1986, 1, 3), date(1986, 1, 6)]
    assert wide["AAA10Y"].iloc[:2].tolist() == [0.9, 0.95]
    assert pd.isna(wide["BAA10Y"].iloc[1]) and pd.isna(wide["AAA10Y"].iloc[2])


def test_load_of_an_unrefreshed_series_is_empty(store):
    assert fred_series.load_fred_series("BAA10Y").empty
    assert fred_series.load_fred_rates().empty


def test_unknown_series_codes_are_rejected(store):
    with pytest.raises(ValueError):
        fred_series.load_fred_series("NOTACODE")
    with pytest.raises(ValueError):
        fred_series.refresh_fred_series(["NOTACODE"])


class _Resp:
    text = "observation_date,BAA10Y\n"

    def raise_for_status(self):
        return None


def test_fetch_sends_no_user_agent_a_timeout_and_cosd_only_when_incremental(monkeypatch):
    seen = []

    def fake_get(url, **kwargs):
        seen.append((url, kwargs))
        return _Resp()

    monkeypatch.setattr(fred_series.requests, "get", fake_get)

    assert fred_series.fetch_fred_csv("BAA10Y") == "observation_date,BAA10Y\n"
    fred_series.fetch_fred_csv("BAA10Y", date(2026, 10, 2))

    (url, full), (_url, incremental) = seen
    assert url == fred_series.FRED_CSV_URL
    assert full["params"] == {"id": "BAA10Y"}
    assert incremental["params"] == {"id": "BAA10Y", "cosd": "2026-10-02"}
    assert "headers" not in full and full["timeout"] > 0
