"""``list_instruments`` reuses parsed files while they are unchanged (#10754).

GET /instrument/admin lists every instrument file; with the screener universe
that is ~12k files, and opening each on every request made the page time out.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.common import instruments as instruments_module
from backend.common.instruments import list_instruments


def _write(path: Path, payload: dict, *, bump_ns: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if bump_ns:
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + bump_ns))


@pytest.fixture
def instruments_dir(tmp_path, monkeypatch):
    root = tmp_path / "instruments"
    _write(root / "L" / "AAA.json", {"ticker": "AAA.L", "name": "Alpha &amp; Co"})
    _write(root / "N" / "BBB.json", {"ticker": "BBB.N", "name": "Beta", "region": "US"})
    (root / "L" / "notes.txt").write_text("not metadata", encoding="utf-8")
    monkeypatch.setattr(instruments_module, "_INSTRUMENTS_DIR", root)
    return root


@pytest.fixture
def load_calls(monkeypatch):
    calls: list[str] = []
    real = instruments_module._load_listed_instrument

    def counting(path: str) -> dict:
        calls.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(instruments_module, "_load_listed_instrument", counting)
    return calls


def _by_ticker(entries):
    return {e["ticker"]: e for e in entries}


def test_lists_every_json_file_with_defaults(instruments_dir):
    entries = _by_ticker(list_instruments())

    assert set(entries) == {"AAA.L", "BBB.N"}
    assert entries["AAA.L"]["name"] == "Alpha & Co"
    assert entries["AAA.L"]["region"] is None
    assert entries["BBB.N"]["region"] == "US"
    for field in ("asset_class", "industry", "grouping"):
        assert entries["BBB.N"][field] is None


def test_unchanged_files_are_not_reopened(instruments_dir, load_calls):
    first = list_instruments()
    second = list_instruments()

    assert sorted(load_calls) == ["AAA.json", "BBB.json"]
    assert _by_ticker(second) == _by_ticker(first)


def test_rewritten_file_is_reread(instruments_dir, load_calls):
    list_instruments()
    _write(instruments_dir / "L" / "AAA.json", {"ticker": "AAA.L", "name": "Renamed"}, bump_ns=10**9)

    entries = _by_ticker(list_instruments())

    assert entries["AAA.L"]["name"] == "Renamed"
    assert sorted(load_calls) == ["AAA.json", "AAA.json", "BBB.json"]


def test_added_and_deleted_files_are_reflected(instruments_dir):
    list_instruments()
    (instruments_dir / "N" / "BBB.json").unlink()
    _write(instruments_dir / "DE" / "CCC.json", {"ticker": "CCC.DE", "name": "Gamma"})

    assert set(_by_ticker(list_instruments())) == {"AAA.L", "CCC.DE"}
    assert not any(p.endswith("BBB.json") for p in instruments_module._LIST_CACHE)


def test_callers_can_mutate_entries_without_affecting_the_cache(instruments_dir):
    first = _by_ticker(list_instruments())
    first["AAA.L"]["name"] = "changed by caller"
    first["AAA.L"]["effective_region"] = "Global"

    again = _by_ticker(list_instruments())

    assert again["AAA.L"]["name"] == "Alpha & Co"
    assert "effective_region" not in again["AAA.L"]


def test_unreadable_file_is_skipped_and_retried(instruments_dir, caplog):
    bad = instruments_dir / "L" / "BAD.json"
    bad.write_text("{not json", encoding="utf-8")

    assert set(_by_ticker(list_instruments())) == {"AAA.L", "BBB.N"}
    assert "Failed to load instrument metadata" in caplog.text

    _write(bad, {"ticker": "BAD.L", "name": "Fixed"}, bump_ns=10**9)
    assert "BAD.L" in _by_ticker(list_instruments())


def test_missing_directory_lists_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(instruments_module, "_INSTRUMENTS_DIR", tmp_path / "absent")
    assert list_instruments() == []


def test_listing_another_root_keeps_this_roots_entries(instruments_dir, tmp_path, monkeypatch, load_calls):
    list_instruments()
    other = tmp_path / "other"
    _write(other / "L" / "ZZZ.json", {"ticker": "ZZZ.L", "name": "Zed"})
    monkeypatch.setattr(instruments_module, "_INSTRUMENTS_DIR", other)
    list_instruments()

    monkeypatch.setattr(instruments_module, "_INSTRUMENTS_DIR", instruments_dir)
    list_instruments()

    assert sorted(load_calls) == ["AAA.json", "BBB.json", "ZZZ.json"]


def test_unreadable_directory_is_logged_not_silent(instruments_dir, monkeypatch, caplog):
    real_scandir = os.scandir

    def deny_n(path):
        if Path(path).name == "N":
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr(instruments_module.os, "scandir", deny_n)

    assert set(_by_ticker(list_instruments())) == {"AAA.L"}
    assert "Cannot list instrument metadata" in caplog.text


def test_cached_only_skips_files_that_are_not_parsed_yet(instruments_dir, load_calls):
    """``cached_only`` lists only parsed files and opens none (#10754)."""
    assert list_instruments(cached_only=True) == []
    assert load_calls == []

    list_instruments()
    _write(instruments_dir / "L" / "AAA.json", {"ticker": "AAA.L", "name": "Changed"}, bump_ns=10**9)
    load_calls.clear()

    assert [e["ticker"] for e in list_instruments(cached_only=True)] == ["BBB.N"]
    assert load_calls == []


def test_admin_route_serves_cached_instruments_while_warming(instruments_dir, load_calls):
    from fastapi import Response

    from backend.common import admin_cache_state
    from backend.routes.instrument_admin import list_instrument_metadata

    admin_cache_state.mark_steps_pending([admin_cache_state.INSTRUMENT_LIST])

    cold = Response()
    assert list_instrument_metadata(cold, partial=True) == []
    assert cold.headers[admin_cache_state.WARMING_HEADER] == "true"

    full = Response()
    assert {e["ticker"] for e in list_instrument_metadata(full, partial=False)} == {"AAA.L", "BBB.N"}
    assert admin_cache_state.WARMING_HEADER not in full.headers

    admin_cache_state.finish_step(admin_cache_state.INSTRUMENT_LIST)
    done = Response()
    assert {e["ticker"] for e in list_instrument_metadata(done, partial=True)} == {"AAA.L", "BBB.N"}
    assert admin_cache_state.WARMING_HEADER not in done.headers
