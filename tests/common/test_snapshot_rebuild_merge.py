"""Startup snapshot rebuild never downgrades a fresher price entry (#10960)."""

import json

import pandas as pd
import pytest

from backend.common import portfolio_utils as pu

_REFRESHED_3IN = {
    "last_price": 3.95,
    "price_currency": "GBP",
    "last_price_date": "2026-10-14",
    "last_price_time": "2026-10-14T15:35:00Z",
    "is_stale": False,
}


def _stub_rebuild(monkeypatch, tmp_path, frames, *, existing, currency="GBP", scale=1):
    """Wire the rebuild to ``frames`` (ticker base -> DataFrame) and an existing prices file."""
    tickers = list(existing) + [t for t in (f"{base}.L" for base in frames) if t not in existing]
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: tickers)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", json.loads(json.dumps(existing)))
    monkeypatch.setattr(pu, "get_instrument_meta", lambda ticker: {"currency": currency})
    monkeypatch.setattr(
        pu,
        "load_meta_timeseries_range",
        lambda *, ticker, exchange, start_date, end_date: frames.get(ticker.upper(), pd.DataFrame()),
    )
    monkeypatch.setattr(pu, "get_scaling_override", lambda ticker, exchange, meta: scale)
    in_memory = {}
    monkeypatch.setattr(pu, "refresh_snapshot_in_memory", lambda snap, ts: in_memory.update(snap))
    prices_path = tmp_path / "latest_prices.json"
    prices_path.write_text(json.dumps(existing))
    monkeypatch.setattr(pu, "_PRICES_PATH", prices_path)
    return prices_path, in_memory


def _closes(date: str, close: float) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime([date]), "Close": [close]})


def test_newer_refresh_entry_survives_older_cache_close(tmp_path, monkeypatch):
    prices_path, in_memory = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 3.945)},
        existing={"3IN.L": _REFRESHED_3IN},
    )

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    assert json.loads(prices_path.read_text())["3IN.L"] == _REFRESHED_3IN
    assert in_memory["3IN.L"] == _REFRESHED_3IN


def test_same_day_refresh_quote_beats_cache_close(tmp_path, monkeypatch):
    prices_path, _ = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-14", 3.9)},
        existing={"3IN.L": _REFRESHED_3IN},
    )

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    assert json.loads(prices_path.read_text())["3IN.L"] == _REFRESHED_3IN


def test_newer_cache_close_replaces_older_entry(tmp_path, monkeypatch):
    older = {**_REFRESHED_3IN, "last_price_date": "2026-10-12", "last_price_time": "2026-10-12T15:35:00Z"}
    prices_path, in_memory = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 3.945)},
        existing={"3IN.L": older},
    )

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    expected = {"last_price": 3.945, "price_currency": "GBP", "last_price_date": "2026-10-13"}
    assert json.loads(prices_path.read_text())["3IN.L"] == expected
    assert in_memory["3IN.L"] == expected


def test_missing_ticker_is_filled_from_cache(tmp_path, monkeypatch):
    prices_path, in_memory = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 3.945), "NEW": _closes("2026-10-13", 2.5)},
        existing={"3IN.L": _REFRESHED_3IN, "PLACEHOLDER.L": {}},
    )

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    written = json.loads(prices_path.read_text())
    assert written["NEW.L"] == {"last_price": 2.5, "price_currency": "GBP", "last_price_date": "2026-10-13"}
    assert written["3IN.L"] == _REFRESHED_3IN
    assert written["PLACEHOLDER.L"] == {}
    assert in_memory["NEW.L"]["last_price"] == pytest.approx(2.5)


def test_pence_instrument_close_is_labelled_gbp_after_scaling(tmp_path, monkeypatch):
    """A GBX close scaled to pounds is stored as GBP, not GBX (#10960)."""
    prices_path, _ = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 394.5)},
        existing={},
        currency="GBX",
        scale=0.01,
    )

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    entry = json.loads(prices_path.read_text())["3IN.L"]
    assert entry["last_price"] == pytest.approx(3.945)
    assert entry["price_currency"] == "GBP"


def test_startup_with_empty_memory_keeps_newer_file_entry(tmp_path, monkeypatch):
    """At startup the in-memory snapshot can still be empty; the file's newer entry must win in memory too."""
    prices_path, in_memory = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 3.945)},
        existing={"3IN.L": _REFRESHED_3IN},
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    assert in_memory["3IN.L"] == _REFRESHED_3IN
    assert json.loads(prices_path.read_text())["3IN.L"] == _REFRESHED_3IN


def test_rebuild_keeps_non_held_entries_in_memory(tmp_path, monkeypatch):
    """Tickers the rebuild doesn't cover (watchlist, price triggers) stay in the in-memory snapshot."""
    watched = {"last_price": 100.0, "price_currency": "GBP", "last_price_date": "2026-10-14", "is_stale": False}
    _, in_memory = _stub_rebuild(
        monkeypatch,
        tmp_path,
        {"3IN": _closes("2026-10-13", 3.945)},
        existing={"WATCHED.L": watched},
    )
    monkeypatch.setattr(pu, "list_all_unique_tickers", lambda: ["3IN.L"])

    pu.refresh_snapshot_in_memory_from_timeseries(days=7)

    assert in_memory["WATCHED.L"] == watched
    assert in_memory["3IN.L"]["last_price"] == pytest.approx(3.945)


@pytest.mark.parametrize(
    ("existing", "rebuilt", "keep_existing"),
    [
        ({"last_price_date": "2026-10-14"}, {"last_price_date": "2026-10-13"}, True),
        ({"last_price_date": "2026-10-13"}, {"last_price_date": "2026-10-14"}, False),
        (
            {"last_price_date": "2026-10-14", "last_price_time": "2026-10-14T15:35:00Z"},
            {"last_price_date": "2026-10-14"},
            True,
        ),
        ({"last_price_date": "2026-10-14"}, {"last_price_date": "2026-10-14"}, False),
        ({}, {"last_price_date": "2026-10-14"}, False),
    ],
)
def test_merge_snapshot_keep_newer(existing, rebuilt, keep_existing):
    merged = pu._merge_snapshot_keep_newer({"T.L": existing}, {"T.L": rebuilt})
    assert merged["T.L"] is (existing if keep_existing else rebuilt)
