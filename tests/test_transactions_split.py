import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


def _seed(tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    txs = [
        {
            "date": "2024-01-01",
            "type": "BUY",
            "ticker": "PFE",
            "units": 10,
            "price_gbp": 2.0,
            "amount_minor": 2000,
            "fees": 1.0,
            "external_id": "HL:1",
        },
        {"date": "2024-02-01", "type": "BUY", "ticker": "KO", "units": 5, "price_gbp": 3.0},
    ]
    (owner_dir / "ISA_transactions.json").write_text(
        json.dumps({"owner": "alice", "account_type": "ISA", "transactions": txs})
    )
    return owner_dir / "ISA_transactions.json"


def test_split_creates_two_rows_with_prorated_totals(tmp_path, monkeypatch):
    path = _seed(tmp_path)
    resp = _client(tmp_path, monkeypatch).post("/transactions/alice:ISA:0/split", json={"units": 4})
    assert resp.status_code == 200
    stored = json.loads(path.read_text())["transactions"]
    assert [t["units"] for t in stored] == [4, 6, 5]
    assert [t["amount_minor"] for t in stored[:2]] == [800.0, 1200.0]
    assert [t["fees"] for t in stored[:2]] == [0.4, 0.6]
    assert stored[0]["price_gbp"] == stored[1]["price_gbp"] == 2.0
    assert stored[0]["external_id"] == "HL:1"
    assert stored[1]["external_id"] == "HL:1#split"
    assert stored[2]["ticker"] == "KO"


def test_split_rejects_units_outside_range(tmp_path, monkeypatch):
    path = _seed(tmp_path)
    before = path.read_text()
    client = _client(tmp_path, monkeypatch)
    for units in (10, 11):
        bad = client.post("/transactions/alice:ISA:0/split", json={"units": units})
        assert bad.status_code == 400
    zero = client.post("/transactions/alice:ISA:0/split", json={"units": 0})
    assert zero.status_code == 422
    assert client.post("/transactions/alice:ISA:9/split", json={"units": 1}).status_code == 404
    assert json.loads(path.read_text()) == json.loads(before)


def test_list_transactions_filters_by_ticker(tmp_path, monkeypatch):
    _seed(tmp_path)
    resp = _client(tmp_path, monkeypatch).get("/transactions", params={"ticker": "pfe"})
    assert [t["ticker"] for t in resp.json()] == ["PFE"]


def test_split_halves_sum_to_original_when_prorating_does_not_divide_evenly(tmp_path, monkeypatch):
    path = _seed(tmp_path)
    data = json.loads(path.read_text())
    data["transactions"][0].update(units=3, amount_minor=1000, fees=0.1)
    path.write_text(json.dumps(data))
    _client(tmp_path, monkeypatch).post("/transactions/alice:ISA:0/split", json={"units": 1})
    first, second = json.loads(path.read_text())["transactions"][:2]
    assert round(first["amount_minor"] + second["amount_minor"], 2) == 1000
    assert round(first["fees"] + second["fees"], 2) == 0.1
