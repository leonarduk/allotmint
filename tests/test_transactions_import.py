import json
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
    assert data[0]["ticker"] == "PFE"
    assert data[0]["owner"] == "alice"


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


def test_moneyhub_parse_unrecognised_columns_yields_empty_fields():
    csv_data = "Foo,Bar\nx,y\n"
    txs = moneyhub.parse(csv_data.encode("utf-8"))
    assert len(txs) == 1
    tx = txs[0]
    assert tx.external_id is None
    assert tx.owner == ""
    assert tx.account == ""
    assert tx.amount_minor is None


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


def test_import_transactions_moneyhub_dedupes_on_reimport(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    key_row1 = "2024-05-01|Current|-42.50|tesco store"
    key_row2 = "2024-05-02|Current|1500.00|salary"

    # First import: nothing persisted yet, so both rows come back as new.
    resp = client.post(
        "/transactions/import",
        data={"provider": "moneyhub"},
        files={"file": ("tx.csv", MONEYHUB_SAMPLE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200
    first = resp.json()
    assert {t["external_id"] for t in first} == {key_row1, key_row2}

    # Persist one of the two rows directly, mimicking what a caller would do
    # after reviewing the parsed-but-not-yet-saved import result.
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir(parents=True)
    (owner_dir / "Current_transactions.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "Current",
                "transactions": [{"external_id": key_row1, "comments": "Tesco Store"}],
            }
        )
    )

    # Re-importing the same export should no longer surface the already
    # persisted row, only the still-new one.
    resp = client.post(
        "/transactions/import",
        data={"provider": "moneyhub"},
        files={"file": ("tx.csv", MONEYHUB_SAMPLE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200
    second = resp.json()
    assert {t["external_id"] for t in second} == {key_row2}
