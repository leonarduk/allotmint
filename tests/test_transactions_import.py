from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import importers
from backend.app import create_app
from backend.config import config
from backend.importers import degiro, moneyhub
from backend.routes.transactions import Transaction

MONEYHUB_SAMPLE = Path(__file__).parent / "data" / "moneyhub_sample.csv"


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    app = create_app()
    return TestClient(app)


def test_import_transactions_csv(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    csv_data = (
        "owner,account,date,ticker,type,price,units,fees,comments,reason_to_buy\n"
        "alice,ISA,2024-05-01,PFE,BUY,10.5,2,1.0,test,diversify\n"
    )
    resp = client.post(
        "/transactions/import",
        data={"provider": "degiro"},
        files={"file": ("tx.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == []
    assert len(data["persisted"]) == 1
    persisted = data["persisted"][0]
    assert persisted["ticker"] == "PFE"
    assert persisted["owner"] == "alice"
    assert persisted["price_gbp"] == 10.5
    assert persisted["units"] == 2
    assert persisted["reason"] == "diversify"
    assert persisted["id"] == "alice:ISA:0"


def test_import_transactions_hargreaves_uses_owner_account_fallback(tmp_path, monkeypatch):
    """Hargreaves rows never carry owner/account of their own (hargreaves.parse()
    always sets them to ""), so the caller must supply a destination
    explicitly via the ``owner``/``account`` form fields (#4965).
    """
    client = _make_client(tmp_path, monkeypatch)
    csv_data = "Code,Units held,Price (pence),Cost (£)\nPFE,2,1050,21.00\n"

    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves", "owner": "alice", "account": "ISA"},
        files={"file": ("tx.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == []
    assert len(data["persisted"]) == 1
    persisted = data["persisted"][0]
    assert persisted["owner"] == "alice"
    assert persisted["account"] == "ISA"
    assert persisted["ticker"] == "PFE"
    assert persisted["price_gbp"] == pytest.approx(10.5)
    assert persisted["units"] == 2


def test_import_transactions_skips_rows_with_no_resolvable_owner_account(tmp_path, monkeypatch):
    """A row with no owner/account of its own, and no fallback supplied, must
    be reported as skipped rather than persisted or silently dropped (#4965).
    """
    client = _make_client(tmp_path, monkeypatch)
    csv_data = "Code,Units held,Price (pence),Cost (£)\nPFE,2,1050,21.00\n"

    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves"},
        files={"file": ("tx.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["persisted"] == []
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["skip_reason"] == "missing owner/account"
    assert data["skipped"][0]["ticker"] == "PFE"


def test_degiro_to_float_invalid_inputs():
    assert degiro._to_float("") is None
    assert degiro._to_float("not-a-number") is None
    assert degiro._to_float(None) is None


def test_degiro_parse_handles_bad_data():
    csv_data = (
        "owner,account,date,ticker,type,price,units\n"
        "bob,ISA,2024-05-02,MSFT,BUY,,oops\n"
    )
    txs = degiro.parse(csv_data.encode("utf-8"))
    assert len(txs) == 1
    tx = txs[0]
    assert tx.price is None
    assert tx.units is None
    assert tx.fees is None
    assert tx.amount_minor is None


def test_moneyhub_parse_fixture():
    txs = moneyhub.parse(MONEYHUB_SAMPLE.read_bytes())
    assert len(txs) == 2
    # No Id column in the fixture, so external_id falls back to the
    # date+account+amount+description composite key (see issue #3426).
    assert txs[0].external_id == "2024-05-01|Current|-42.50|tesco store"
    assert txs[0].owner == "alice"
    assert txs[0].account == "Current"
    assert txs[0].amount_minor == pytest.approx(-42.50)
    assert txs[0].comments == "Tesco Store"
    assert txs[0].type == "Groceries"


def test_moneyhub_parse_uses_id_column_when_present():
    csv_data = (
        "Id,Owner,Account,Date,Amount,Description,Category\n"
        "mh-1001,alice,Current,2024-05-01,-42.50,Tesco Store,Groceries\n"
    )
    txs = moneyhub.parse(csv_data.encode("utf-8"))
    assert txs[0].external_id == "mh-1001"


def test_moneyhub_composite_key_requires_date_and_amount():
    assert moneyhub._composite_key(None, "Current", -42.50, "Tesco") is None
    assert moneyhub._composite_key("2024-05-01", "Current", None, "Tesco") is None
    assert moneyhub._composite_key("2024-05-01", "Current", -42.50, "Tesco") == "2024-05-01|Current|-42.50|tesco"


def test_moneyhub_to_float_invalid_inputs():
    assert moneyhub._to_float("") is None
    assert moneyhub._to_float("not-a-number") is None
    assert moneyhub._to_float(None) is None


def test_moneyhub_parse_empty_csv_returns_no_transactions():
    csv_data = "Id,Owner,Account,Date,Amount,Description,Category\n"
    assert moneyhub.parse(csv_data.encode("utf-8")) == []


def test_moneyhub_parse_rejects_csv_with_unrecognised_columns():
    csv_data = "Foo,Bar\nx,y\n"
    with pytest.raises(ValueError, match="missing required columns"):
        moneyhub.parse(csv_data.encode("utf-8"))


def test_moneyhub_parse_rejects_csv_missing_some_required_columns():
    csv_data = "Owner,Account\nalice,Current\n"
    with pytest.raises(ValueError) as exc_info:
        moneyhub.parse(csv_data.encode("utf-8"))
    message = str(exc_info.value)
    assert "date" in message
    assert "amount" in message


def test_moneyhub_parse_rejects_empty_csv():
    with pytest.raises(ValueError, match="missing required columns"):
        moneyhub.parse(b"")


@pytest.mark.parametrize("id_header", ["Id", "id", "ID", "iD"])
def test_moneyhub_parse_header_matching_is_case_insensitive_for_id(id_header):
    csv_data = (
        f"{id_header},Owner,Account,Date,Amount,Description,Category\n"
        "mh-1001,alice,Current,2024-05-01,-42.50,Tesco Store,Groceries\n"
    )
    txs = moneyhub.parse(csv_data.encode("utf-8"))
    assert txs[0].external_id == "mh-1001"


def test_moneyhub_parse_header_matching_is_case_insensitive_for_required_columns():
    csv_data = "OWNER,ACCOUNT,DATE,AMOUNT,description,category\nalice,Current,2024-05-01,-42.50,Tesco,Groceries\n"
    txs = moneyhub.parse(csv_data.encode("utf-8"))
    assert len(txs) == 1
    assert txs[0].owner == "alice"
    assert txs[0].account == "Current"
    assert txs[0].amount_minor == pytest.approx(-42.50)


def _tx(external_id=None, **kwargs):
    return Transaction(owner="alice", account="ISA", external_id=external_id, **kwargs)


def test_dedupe_against_existing_returns_all_when_existing_empty():
    candidates = [_tx(external_id="a"), _tx(external_id="b")]
    assert importers.dedupe_against_existing(candidates, []) == candidates


def test_dedupe_against_existing_returns_empty_when_candidates_empty():
    assert importers.dedupe_against_existing([], [_tx(external_id="a")]) == []


def test_dedupe_against_existing_filters_matching_external_ids():
    candidates = [_tx(external_id="a"), _tx(external_id="b")]
    existing = [_tx(external_id="a")]
    result = importers.dedupe_against_existing(candidates, existing)
    assert [t.external_id for t in result] == ["b"]


def test_dedupe_against_existing_treats_missing_external_id_as_always_new():
    candidate = _tx(external_id=None)
    existing = [_tx(external_id=None)]
    result = importers.dedupe_against_existing([candidate], existing)
    assert result == [candidate]


def test_import_transactions_moneyhub_persists_and_dedupes_on_reimport(tmp_path, monkeypatch):
    """Import -> persist -> re-import must show zero duplicates end-to-end (#4965).

    Unlike the old version of this test, nothing is hand-written to the
    accounts store to simulate a prior import: both rounds go through the
    real ``/transactions/import`` persistence path, so a regression in that
    path (e.g. dedupe checking the wrong store) would actually be caught.
    """
    client = _make_client(tmp_path, monkeypatch)
    key_row1 = "2024-05-01|Current|-42.50|tesco store"
    key_row2 = "2024-05-02|Current|1500.00|salary"

    # First import: nothing persisted yet, so both bank-style rows (no
    # ticker/price/units -- Moneyhub) are persisted as-is.
    resp = client.post(
        "/transactions/import",
        data={"provider": "moneyhub"},
        files={"file": ("tx.csv", MONEYHUB_SAMPLE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200
    first = resp.json()
    assert first["skipped"] == []
    assert {t["external_id"] for t in first["persisted"]} == {key_row1, key_row2}
    assert all(t["owner"] == "alice" for t in first["persisted"])

    # Re-importing the same export must persist nothing further: both rows
    # are already in storage, so dedupe filters them out before persistence
    # is ever attempted.
    resp = client.post(
        "/transactions/import",
        data={"provider": "moneyhub"},
        files={"file": ("tx.csv", MONEYHUB_SAMPLE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"persisted": [], "skipped": []}
