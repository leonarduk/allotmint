from __future__ import annotations

import json
from datetime import date

import pytest

from backend.common.approvals import (
    add_trading_days,
    delete_approval,
    is_approval_valid,
    load_approvals,
    needs_sell_approval,
    save_approvals,
    upsert_approval,
)
from backend.config import config


def _owner_dir(tmp_path, owner: str):
    path = tmp_path / owner
    path.mkdir()
    return path


def test_load_approvals_handles_variants_and_invalid_rows(tmp_path):
    list_owner = "list-owner"
    list_dir = _owner_dir(tmp_path, list_owner)
    (list_dir / "approvals.json").write_text(
        json.dumps(
            [
                {"ticker": "abc", "approved_on": "2024-04-03"},
                {"ticker": "def", "approved_on": "not-a-date"},
            ]
        )
    )

    dict_owner = "dict-owner"
    dict_dir = _owner_dir(tmp_path, dict_owner)
    (dict_dir / "approvals.json").write_text(json.dumps({"approvals": [{"ticker": "msft", "date": "2024-04-02"}]}))

    malformed_owner = "broken-owner"
    malformed_dir = _owner_dir(tmp_path, malformed_owner)
    (malformed_dir / "approvals.json").write_text("{this is not valid json")

    empty_owner = "empty-owner"
    _owner_dir(tmp_path, empty_owner)

    assert load_approvals(list_owner, tmp_path) == {
        "ABC": date(2024, 4, 3)
    }, "valid rows should be parsed and normalised to uppercase"

    assert load_approvals(dict_owner, tmp_path) == {
        "MSFT": date(2024, 4, 2)
    }, "dict payloads should be supported and tickers uppercased"

    assert load_approvals(malformed_owner, tmp_path) == {}, "malformed JSON should yield an empty approvals map"

    assert load_approvals(empty_owner, tmp_path) == {}, "missing approvals file should return empty map"


def test_trading_days_and_validity_calculations(monkeypatch):
    monkeypatch.setattr(config, "approval_valid_days", 2)

    start = date(2024, 4, 5)  # Friday
    assert add_trading_days(start, 1) == date(2024, 4, 8), "weekend should be skipped"

    approved_on = date(2024, 4, 5)
    assert is_approval_valid(approved_on, date(2024, 4, 8))
    assert not is_approval_valid(approved_on, date(2024, 4, 9))

    assert is_approval_valid(approved_on, date(2024, 4, 5), days=1)
    assert not is_approval_valid(approved_on, date(2024, 4, 8), days=1)

    assert not is_approval_valid(None, date(2024, 4, 5))


def test_save_and_mutate_approvals(tmp_path):
    owner = "carol"
    owner_dir = _owner_dir(tmp_path, owner)

    initial = {"msft": date(2024, 4, 1), "aapl": date(2024, 4, 2)}
    save_approvals(owner, initial, tmp_path)

    saved = json.loads((owner_dir / "approvals.json").read_text())
    assert sorted(saved["approvals"], key=lambda e: e["ticker"]) == [
        {"ticker": "AAPL", "approved_on": "2024-04-02"},
        {"ticker": "MSFT", "approved_on": "2024-04-01"},
    ]

    updated = upsert_approval(owner, "tsla", date(2024, 4, 3), tmp_path)
    assert updated == {
        "AAPL": date(2024, 4, 2),
        "MSFT": date(2024, 4, 1),
        "TSLA": date(2024, 4, 3),
    }

    updated = upsert_approval(owner, "aapl", date(2024, 4, 4), tmp_path)
    assert updated["AAPL"] == date(2024, 4, 4)

    updated = delete_approval(owner, "tsla", tmp_path)
    assert "TSLA" not in updated

    final = json.loads((owner_dir / "approvals.json").read_text())
    assert sorted(final["approvals"], key=lambda e: e["ticker"]) == [
        {"ticker": "AAPL", "approved_on": "2024-04-04"},
        {"ticker": "MSFT", "approved_on": "2024-04-01"},
    ]


_GOLD_ETC = {"instrumentType": "ETC", "asset_class": "commodity", "sector": "Commodities"}
_GOLD_ETF_BY_SECTOR = {"instrumentType": "ETF", "sector": "Commodities"}
_EQUITY_ETF = {"instrumentType": "ETF", "asset_class": "equity", "sector": "Multi-sector"}


@pytest.mark.parametrize(
    "meta,exempt_types,exempt_tickers,expected",
    [
        # #10560: exempting ETC must not exempt a commodity ETC.
        (_GOLD_ETC, ["ETF", "ETC"], [], True),
        # #10560: a "Commodities" sector counts even without asset_class.
        (_GOLD_ETF_BY_SECTOR, ["ETF"], [], True),
        (_EQUITY_ETF, ["ETF"], [], False),
        (_EQUITY_ETF, ["etf"], [], False),  # case-insensitive type match
        (_EQUITY_ETF, [], [], True),
        ({"instrumentType": "Equity"}, ["ETF"], [], True),
        # An explicit per-ticker exemption still wins, commodity or not.
        (_GOLD_ETC, ["ETF"], ["phgp.l"], False),
        (_GOLD_ETC, None, None, True),
    ],
)
def test_needs_sell_approval(meta, exempt_types, exempt_tickers, expected):
    assert needs_sell_approval(meta, ("PHGP", "PHGP.L"), exempt_types, exempt_tickers) is expected
