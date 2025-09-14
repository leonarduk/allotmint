import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.importers import hargreaves
from backend.utils import update_holdings_from_csv
from backend.app import create_app
from backend.config import config


SAMPLE_CSV = (
    "Code,Stock,Units held,Price (pence),Cost (£)\n"
    "AAA,Alpha,10,150,15\n"
    "BBB,Beta,5,200,10\n"
)


def test_hargreaves_parse():
    txs = hargreaves.parse(SAMPLE_CSV.encode())
    assert len(txs) == 2
    first = txs[0]
    assert first.ticker == "AAA"
    assert first.units == 10
    assert first.price == pytest.approx(1.5)
    assert first.amount_minor == pytest.approx(1500)


def test_update_holdings_from_csv(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    result = update_holdings_from_csv.update_from_csv(
        owner="alice",
        account="isa",
        provider="hargreaves",
        data=SAMPLE_CSV.encode(),
    )
    acct_file = tmp_path / "alice" / "isa.json"
    assert acct_file.exists()
    data = json.loads(acct_file.read_text())
    assert len(data["holdings"]) == 2
    h = {h["ticker"]: h for h in data["holdings"]}
    assert h["AAA"]["units"] == 10
    assert h["AAA"]["cost_basis_gbp"] == 15
    assert h["AAA"]["current_price_gbp"] == pytest.approx(1.5)
    assert result["account_type"].lower() == "isa"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    app.state.accounts_root = tmp_path
    with TestClient(app) as c:
        yield c


def test_holdings_import_endpoint(client: TestClient, tmp_path: Path):
    files = {"file": ("holdings.csv", SAMPLE_CSV.encode())}
    data = {"provider": "hargreaves", "owner": "alice", "account": "isa"}
    resp = client.post("/holdings/import", data=data, files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_type"].lower() == "isa"
    assert (tmp_path / "alice" / "isa.json").exists()
