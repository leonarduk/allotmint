from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


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
