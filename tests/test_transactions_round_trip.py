import json
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.config import config


@pytest.fixture
def client(tmp_path):
    old_root = config.accounts_root
    old_offline = config.offline_mode
    config.accounts_root = tmp_path
    config.offline_mode = True
    app = create_app()
    with TestClient(app) as c:
        yield c
    config.accounts_root = old_root
    config.offline_mode = old_offline


def test_transaction_round_trip(client, tmp_path):
    owner_dir = tmp_path / "sam"
    owner_dir.mkdir()
    data = {
        "owner": "sam",
        "account_type": "ISA",
        "transactions": [
            {
                "date": "2024-06-10",
                "ticker": "SAMP",
                "type": "buy",
                "price": 10.5,
                "units": 5,
                "fees": 1.5,
                "comments": "long term",
                "reason_to_buy": "dividend",
            }
        ],
    }
    (owner_dir / "isa_transactions.json").write_text(json.dumps(data))

    resp = client.get("/transactions")
    assert resp.status_code == 200
    txs = resp.json()
    assert len(txs) == 1
    tx = txs[0]
    assert tx["price"] == 10.5
    assert tx["units"] == 5
    assert tx["fees"] == 1.5
    assert tx["comments"] == "long term"
    assert tx["reason_to_buy"] == "dividend"
