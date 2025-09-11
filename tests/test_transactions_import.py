from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.importers import degiro


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    app = create_app()
    return TestClient(app)


def test_import_transactions_csv(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    csv_data = (
        "owner,account,date,ticker,type,price,units,fees,comments,reason_to_buy\n"
        "alice,ISA,2024-05-01,AAPL,BUY,10.5,2,1.0,test,diversify\n"
    )
    resp = client.post(
        "/transactions/import",
        data={"provider": "degiro"},
        files={"file": ("tx.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["ticker"] == "AAPL"
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
