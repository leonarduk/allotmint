"""Extra tickers for the scheduled price refresh (#10624)."""

import json
import logging

import pytest

from backend.common import prices, refresh_extra
from backend.common.refresh_extra import extra_refresh_tickers


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.delenv(refresh_extra.URI_ENV, raising=False)
    monkeypatch.setattr(refresh_extra.config, "data_root", tmp_path)
    return tmp_path


def _write(root, payload):
    (root / refresh_extra.FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def test_no_file_means_no_extras(data_root):
    assert extra_refresh_tickers() == []


def test_reads_canonical_deduplicated_tickers(data_root):
    _write(data_root, {"tickers": ["spy.n", "VWRL.L", "BP.", "SPY.N", "", 7]})
    assert extra_refresh_tickers() == ["SPY.N", "VWRL.L", "BP.L"]


def test_bare_list_is_accepted(data_root):
    _write(data_root, ["SMH.N"])
    assert extra_refresh_tickers() == ["SMH.N"]


@pytest.mark.parametrize(
    "payload", [{"tickers": "SPY.N"}, {"tickers": None}, {"tickers": 5}, {"other": []}, "SPY.N", 5]
)
def test_wrong_shape_is_ignored_with_a_warning(data_root, payload, caplog):
    _write(data_root, payload)
    with caplog.at_level(logging.WARNING):
        assert extra_refresh_tickers() == []
    assert "expected" in caplog.text


def test_invalid_json_is_ignored(data_root):
    (data_root / refresh_extra.FILENAME).write_text("{not json", encoding="utf-8")
    assert extra_refresh_tickers() == []


def test_storage_failure_never_raises(data_root, monkeypatch, caplog):
    def boom(uri):
        raise RuntimeError("bucket gone")

    monkeypatch.setattr(refresh_extra, "get_storage", boom)
    with caplog.at_level(logging.WARNING):
        assert extra_refresh_tickers() == []
    assert "bucket gone" in caplog.text


def test_explicit_uri_wins(tmp_path, monkeypatch, data_root):
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"tickers": ["QQQ.N"]}), encoding="utf-8")
    _write(data_root, {"tickers": ["SPY.N"]})
    monkeypatch.setenv(refresh_extra.URI_ENV, f"file://{elsewhere}")
    assert extra_refresh_tickers() == ["QQQ.N"]


def test_refresh_universe_unions_holdings_triggers_and_extras(monkeypatch):
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["VWRL.L", "BP.L"])
    monkeypatch.setattr(prices.price_triggers, "watched_tickers", lambda: ["SPY.N"])
    monkeypatch.setattr(prices, "extra_refresh_tickers", lambda: ["SPY.N", "SMH.N", "BP.L"])
    assert prices.refresh_universe() == ["BP.L", "SMH.N", "SPY.N", "VWRL.L"]


def test_refresh_universe_unchanged_without_extras(monkeypatch):
    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: ["VWRL.L"])
    monkeypatch.setattr(prices.price_triggers, "watched_tickers", lambda: [])
    monkeypatch.setattr(prices, "extra_refresh_tickers", lambda: [])
    assert prices.refresh_universe() == ["VWRL.L"]
