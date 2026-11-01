"""Bulk CSV import of purchase prices (#10095). Synthetic owners/tickers only."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.accounts_store import LocalAccountsStore
from backend.common.cost_basis_import import (
    COST_BASIS_IMPORT_REASON,
    CostBasisCsvError,
    PurchaseLot,
    parse_purchase_lots,
    plan_cost_basis_lots,
)
from backend.config import config
from backend.routes import transactions


def _lot(units, unit_cost=2.0, ticker="AAA.L", day="2020-01-02", line=2):
    return PurchaseLot(line=line, ticker=ticker, date=day, units=units, unit_cost=unit_cost)


# ---- parse_purchase_lots ---------------------------------------------------


def test_parse_reads_aliased_headers_uk_dates_and_currency_formatting():
    csv = "﻿Symbol,Purchase Date,Quantity,Unit Price,Account\n" 'aaa.l,02/01/2020,"1,000",£2.50,ISA\n'

    lots, skipped = parse_purchase_lots(csv.encode())

    assert skipped == []
    assert lots == [PurchaseLot(line=2, ticker="AAA.L", date="2020-01-02", units=1000.0, unit_cost=2.5, account="ISA")]


def test_parse_skips_bad_rows_with_reasons_and_ignores_blank_lines():
    csv = (
        "ticker,date,units,unit_cost\n"
        "AAA.L,2020-01-02,10,2\n"
        ",,,\n"
        "BBB.L,not-a-date,10,2\n"
        "CCC.L,2020-01-02,-1,2\n"
        "DDD.L,2020-01-02,10,abc\n"
        "EEE.L,2999-01-01,10,2\n"
        ",2020-01-02,10,2\n"
    )

    lots, skipped = parse_purchase_lots(csv.encode(), latest=date(2026, 1, 1))

    assert [lot.ticker for lot in lots] == ["AAA.L"]
    reasons = {row["line"]: row["skip_reason"] for row in skipped}
    assert set(reasons) == {4, 5, 6, 7, 8}
    assert "not YYYY-MM-DD" in reasons[4]
    assert reasons[5] == "units must be greater than 0"
    assert "not a number" in reasons[6]
    assert reasons[7] == "date cannot be in the future"
    assert reasons[8] == "ticker is required"


def test_parse_rejects_a_file_missing_required_columns():
    with pytest.raises(CostBasisCsvError, match="unit_cost"):
        parse_purchase_lots(b"ticker,date,units\nAAA.L,2020-01-02,1\n")


def test_parse_rejects_non_utf8_bytes():
    with pytest.raises(CostBasisCsvError):
        parse_purchase_lots(b"\xff\xfe\x00bad")


# ---- plan_cost_basis_lots --------------------------------------------------


def test_plan_writes_priced_transfers_for_an_untracked_holding():
    holdings = [{"ticker": "AAA.L", "units": 15}]

    txs, reason = plan_cost_basis_lots([], holdings, "AAA.L", [_lot(10, 2.0), _lot(5, 3.0, day="2021-06-01")])

    assert reason is None
    assert [(t["type"], t["ticker"], t["date"], t["units"], t["price_gbp"]) for t in txs] == [
        ("TRANSFER_IN", "AAA.L", "2020-01-02", 10, 2.0),
        ("TRANSFER_IN", "AAA.L", "2021-06-01", 5.0, 3.0),
    ]
    assert all(t["reason"] == COST_BASIS_IMPORT_REASON for t in txs)


def test_plan_matches_tickers_canonically_and_uses_the_stored_spelling():
    txs, reason = plan_cost_basis_lots([], [{"ticker": "BP.", "units": 4}], "BP.L", [_lot(4, ticker="BP.L")])

    assert reason is None
    assert txs[0]["ticker"] == "BP."


def test_plan_absorbs_float_noise_so_units_are_unchanged():
    txs, reason = plan_cost_basis_lots(
        [], [{"ticker": "AAA.L", "units": 0.3}], "AAA.L", [_lot(0.1), _lot(0.2000000001)]
    )

    assert reason is None
    assert sum(t["units"] for t in txs) == pytest.approx(0.3, abs=1e-12)


def test_plan_skips_lots_whose_last_lot_would_be_negative():
    # Within the float tolerance overall, but the earlier lots already exceed the units held.
    txs, reason = plan_cost_basis_lots(
        [], [{"ticker": "AAA.L", "units": 10}], "AAA.L", [_lot(10.0000001), _lot(0.0000001)]
    )

    assert txs == []
    assert reason is not None and "last lot would leave no units" in reason


def test_plan_skips_a_holding_not_on_file():
    txs, reason = plan_cost_basis_lots([], [], "AAA.L", [_lot(1)])

    assert txs == []
    assert reason == "no AAA.L holding in this account"


def test_plan_skips_lots_that_do_not_cover_the_units_held():
    txs, reason = plan_cost_basis_lots([], [{"ticker": "AAA.L", "units": 10}], "AAA.L", [_lot(4)])

    assert txs == []
    assert reason == "lot units add up to 4, but 10 units are held"


def test_plan_skips_a_holding_the_ledger_already_tracks():
    ledger = [{"type": "TRANSFER_IN", "ticker": "AAA.L", "date": "2020-01-01", "units": 10}]

    txs, reason = plan_cost_basis_lots(ledger, [{"ticker": "AAA.L", "units": 10}], "AAA.L", [_lot(10)])

    assert txs == []
    assert "already has transactions" in reason


# ---- POST /holdings/cost-basis/import --------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


def _write_account(tmp_path, owner, account, holdings, transactions=None):
    owner_dir = tmp_path / owner
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / f"{account}.json").write_text(
        json.dumps({"owner": owner, "account_type": account, "currency": "GBP", "holdings": holdings})
    )
    if transactions is not None:
        (owner_dir / f"{account}_transactions.json").write_text(json.dumps({"transactions": transactions}))


def _holdings(tmp_path, owner, account):
    doc = json.loads((tmp_path / owner / f"{account}.json").read_text())
    return {h["ticker"]: h for h in doc["holdings"]}


def _post(client, csv, **form):
    return client.post("/holdings/cost-basis/import", data=form, files={"file": ("lots.csv", csv.encode())})


def test_import_fills_cost_for_matched_holdings_without_changing_units(client, tmp_path):
    _write_account(
        tmp_path,
        "testowner",
        "isa",
        [
            {"ticker": "AAA.L", "units": 15, "cost_basis_gbp": 0, "value_gbp": 60},
            {"ticker": "BBB.L", "units": 8, "cost_basis_gbp": 0},
        ],
    )
    csv = "ticker,date,units,unit_cost\nAAA.L,2020-01-02,10,2\nAAA.L,2021-06-01,5,3\nBBB.L,2019-03-04,8,1.25\n"

    resp = _post(client, csv, owner="testowner", account="ISA")

    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] == []
    assert {(u["ticker"], u["units"], u["cost_basis_gbp"], u["lots"]) for u in body["updated"]} == {
        ("AAA.L", 15, 35.0, 2),
        ("BBB.L", 8, 10.0, 1),
    }
    held = _holdings(tmp_path, "testowner", "isa")
    assert (held["AAA.L"]["units"], held["AAA.L"]["cost_basis_gbp"]) == (15, 35.0)
    assert held["AAA.L"]["acquired_date"] == "2021-06-01"
    assert held["AAA.L"]["value_gbp"] == 60
    assert (held["BBB.L"]["units"], held["BBB.L"]["cost_basis_gbp"]) == (8, 10.0)


def test_reimporting_the_same_csv_never_doubles_units(client, tmp_path):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 10, "cost_basis_gbp": 0}])
    csv = "ticker,date,units,unit_cost\nAAA.L,2020-01-02,10,2\n"
    assert _post(client, csv, owner="testowner", account="isa").json()["updated"]

    again = _post(client, csv, owner="testowner", account="isa").json()

    assert again["updated"] == []
    assert "already has transactions" in again["skipped"][0]["skip_reason"]
    assert _holdings(tmp_path, "testowner", "isa")["AAA.L"]["units"] == 10
    ledger = json.loads((tmp_path / "testowner" / "isa_transactions.json").read_text())["transactions"]
    assert len(ledger) == 1


def test_import_routes_rows_by_account_column_and_reports_unmatched(client, tmp_path):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 1}])
    _write_account(tmp_path, "testowner", "sipp", [{"ticker": "CCC.L", "units": 2}])
    csv = (
        "account,ticker,date,units,unit_cost\n"
        "isa,AAA.L,2020-01-02,1,5\n"
        "SIPP,CCC.L,2020-01-02,2,7\n"
        "sipp,ZZZ.L,2020-01-02,2,7\n"
        ",AAA.L,2020-01-02,1,5\n"
    )

    body = _post(client, csv, owner="testowner").json()

    assert {(u["account"], u["ticker"]) for u in body["updated"]} == {("isa", "AAA.L"), ("sipp", "CCC.L")}
    assert {(s["line"], s["skip_reason"]) for s in body["skipped"]} == {
        (5, "missing owner/account"),
        (4, "no ZZZ.L holding in this account"),
    }
    assert _holdings(tmp_path, "testowner", "sipp")["CCC.L"]["cost_basis_gbp"] == 14.0


def test_import_rejects_a_file_without_required_columns(client):
    resp = _post(client, "ticker,units\nAAA.L,1\n", owner="testowner", account="isa")

    assert resp.status_code == 400
    assert "Missing column" in resp.json()["detail"]


def test_import_rolls_back_every_account_when_a_rebuild_fails(client, tmp_path, monkeypatch):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 1}])
    _write_account(tmp_path, "testowner", "sipp", [{"ticker": "CCC.L", "units": 2}])
    real_rebuild = transactions._rebuild_portfolio
    calls = []

    def flaky_rebuild(owner, account, store):
        calls.append(account)
        real_rebuild(owner, account, store)
        if account == "sipp" and calls.count("sipp") == 1:
            # The holdings were written from the import's rows before the failure.
            raise RuntimeError("boom")

    monkeypatch.setattr(transactions, "_rebuild_portfolio", flaky_rebuild)
    csv = "account,ticker,date,units,unit_cost\nisa,AAA.L,2020-01-02,1,5\nsipp,CCC.L,2020-01-02,2,7\n"

    with pytest.raises(RuntimeError, match="boom"):
        _post(client, csv, owner="testowner")

    for account in ("isa", "sipp"):
        ledger = json.loads((tmp_path / "testowner" / f"{account}_transactions.json").read_text())
        assert ledger["transactions"] == []
    # The account whose rebuild failed is rebuilt again after its rows are removed.
    assert calls.count("sipp") == 2
    # Neither account's holdings keep the rolled-back import's cost (#11227): both are
    # back to what they were before the import, which a fresh rebuild leaves unchanged.
    for account, ticker in (("isa", "AAA.L"), ("sipp", "CCC.L")):
        after_rollback = _holdings(tmp_path, "testowner", account)
        assert "cost_basis_gbp" not in after_rollback[ticker]
        assert "acquired_date" not in after_rollback[ticker]
        assert after_rollback[ticker]["units"] == {"isa": 1, "sipp": 2}[account]
        real_rebuild("testowner", account, LocalAccountsStore(root=tmp_path))
        assert _holdings(tmp_path, "testowner", account) == after_rollback


def test_import_raises_the_rebuild_error_when_the_recovery_rebuild_also_fails(client, tmp_path, monkeypatch):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 1}])
    calls = []

    def failing_rebuild(owner, account, store):
        calls.append(account)
        raise RuntimeError("boom" if len(calls) == 1 else "recovery failed")

    monkeypatch.setattr(transactions, "_rebuild_portfolio", failing_rebuild)

    with pytest.raises(RuntimeError, match="^boom$"):
        _post(client, "ticker,date,units,unit_cost\nAAA.L,2020-01-02,1,5\n", owner="testowner", account="isa")

    assert calls == ["isa", "isa"]
    ledger = json.loads((tmp_path / "testowner" / "isa_transactions.json").read_text())
    assert ledger["transactions"] == []


def test_import_refuses_when_the_ledger_changes_after_planning(client, tmp_path, monkeypatch):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 10, "cost_basis_gbp": 0}])
    ledger = tmp_path / "testowner" / "isa_transactions.json"
    real_plan = transactions._plan_account_lots

    def plan_then_concurrent_write(*args, **kwargs):
        planned = real_plan(*args, **kwargs)
        # Another request records a trade for the same holding before the import takes the lock.
        trade = {"type": "BUY", "ticker": "AAA.L", "date": "2024-01-02", "units": 10, "price_gbp": 4}
        ledger.write_text(json.dumps({"transactions": [trade]}))
        return planned

    monkeypatch.setattr(transactions, "_plan_account_lots", plan_then_concurrent_write)
    csv = "ticker,date,units,unit_cost\nAAA.L,2020-01-02,10,2\n"

    resp = _post(client, csv, owner="testowner", account="isa")

    assert resp.status_code == 409
    assert [t["type"] for t in json.loads(ledger.read_text())["transactions"]] == ["BUY"]


def test_parse_hides_unexpected_row_errors(monkeypatch):
    from backend.common import cost_basis_import as mod

    def boom(*_args, **_kwargs):
        raise ValueError("internal detail /srv/secret.py line 9")

    monkeypatch.setattr(mod, "_lot_from_row", boom)

    lots, skipped = parse_purchase_lots(b"ticker,date,units,unit_cost\nAAA.L,2020-01-02,1,2\n")

    assert lots == []
    assert skipped[0]["skip_reason"] == "row could not be read"


def test_plan_skips_a_last_lot_that_rounds_to_zero():
    txs, reason = plan_cost_basis_lots([], [{"ticker": "AAA.L", "units": 10}], "AAA.L", [_lot(10 - 1e-9), _lot(1e-9)])

    assert txs == []
    assert reason is not None and "last lot would leave no units" in reason


def test_rollback_removes_only_the_import_rows_after_an_earlier_row_is_deleted(client, tmp_path, monkeypatch):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 1}])
    ledger = tmp_path / "testowner" / "isa_transactions.json"
    other = {"type": "DIVIDEND", "ticker": "ZZZ.L", "date": "2019-05-01", "amount_minor": 100}
    kept = {"type": "DIVIDEND", "ticker": "YYY.L", "date": "2019-06-01", "amount_minor": 200}
    ledger.write_text(json.dumps({"transactions": [other, kept]}))
    real_rebuild = transactions._rebuild_portfolio
    calls = []

    def delete_earlier_row_then_fail(owner, account, store):
        calls.append(account)
        if len(calls) == 1:
            # Another request deletes an earlier row after the import appended its rows,
            # so the import's rows no longer start at the index it recorded.
            data = json.loads(ledger.read_text())
            data["transactions"].pop(0)
            ledger.write_text(json.dumps(data))
            raise RuntimeError("boom")
        real_rebuild(owner, account, store)

    monkeypatch.setattr(transactions, "_rebuild_portfolio", delete_earlier_row_then_fail)
    csv = "ticker,date,units,unit_cost\nAAA.L,2020-01-02,1,5\n"

    with pytest.raises(RuntimeError, match="boom"):
        _post(client, csv, owner="testowner", account="isa")

    # The unrelated row survives; only the import's TRANSFER_IN is removed.
    assert json.loads(ledger.read_text())["transactions"] == [kept]


def test_find_appended_prefers_the_recorded_index_then_searches_from_the_end():
    rows = [{"type": "TRANSFER_IN", "ticker": "AAA.L"}]
    other = {"type": "BUY", "ticker": "BBB.L"}

    assert transactions._find_appended([other, rows[0]], 1, rows) == 1
    assert transactions._find_appended([rows[0], other], 1, rows) == 0
    assert transactions._find_appended([other], 1, rows) is None


def test_import_checks_owner_access_for_every_owner_before_writing(client, tmp_path, monkeypatch):
    from backend.common.errors import PermissionDeniedError

    _write_account(tmp_path, "alex", "isa", [{"ticker": "AAA.L", "units": 1}])
    _write_account(tmp_path, "bob", "isa", [{"ticker": "BBB.L", "units": 1}])
    checked = []

    def deny_bob(identity, owner, accounts_root=None):
        checked.append(owner)
        if owner == "bob":
            raise PermissionDeniedError("nope")

    monkeypatch.setattr(transactions, "ensure_owner_access", deny_bob)
    csv = "owner,account,ticker,date,units,unit_cost\nalex,isa,AAA.L,2020-01-02,1,5\nbob,isa,BBB.L,2020-01-02,1,7\n"

    resp = _post(client, csv)

    assert resp.status_code == 403
    assert checked == ["alex", "bob"]
    # Nothing is written for the permitted owner either: access is checked first.
    assert not (tmp_path / "alex" / "isa_transactions.json").exists()


def test_import_refuses_when_the_holdings_change_after_planning(client, tmp_path, monkeypatch):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 10, "cost_basis_gbp": 0}])
    real_plan = transactions._plan_account_lots

    def plan_then_manual_holding_edit(*args, **kwargs):
        planned = real_plan(*args, **kwargs)
        # A manual holding edit changes units without adding a transaction.
        _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 12, "cost_basis_gbp": 0}])
        return planned

    monkeypatch.setattr(transactions, "_plan_account_lots", plan_then_manual_holding_edit)
    csv = "ticker,date,units,unit_cost\nAAA.L,2020-01-02,10,2\n"

    resp = _post(client, csv, owner="testowner", account="isa")

    assert resp.status_code == 409
    assert not (tmp_path / "testowner" / "isa_transactions.json").exists()
    assert _holdings(tmp_path, "testowner", "isa")["AAA.L"]["units"] == 12
