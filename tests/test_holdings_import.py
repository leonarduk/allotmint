import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.importers import hargreaves
from backend.utils import update_holdings_from_csv

SAMPLE_CSV = "Code,Stock,Units held,Price (pence),Cost (£)\n" "AAA,Alpha,10,150,15\n" "BBB,Beta,5,200,10\n"


def test_hargreaves_parse():
    txs = hargreaves.parse(SAMPLE_CSV.encode())
    assert len(txs) == 2
    first = txs[0]
    assert first.ticker == "AAA"
    assert first.units == 10
    assert first.price == pytest.approx(1.5)
    assert first.amount_minor == pytest.approx(1500)


def test_hargreaves_to_float_variants():
    # None or blank strings should resolve to ``None`` without raising.
    assert hargreaves._to_float(None) is None
    assert hargreaves._to_float("   ") is None

    # Comma separated numbers should be normalised before conversion.
    assert hargreaves._to_float("1,234.56") == pytest.approx(1234.56)

    # Malformed numeric values should be ignored gracefully.
    assert hargreaves._to_float("not-a-number") is None


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
    assert Path(result["path"]).resolve() == acct_file.resolve()


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
    acct_file = tmp_path / "alice" / "isa.json"
    assert Path(body["path"]).resolve() == acct_file.resolve()
    assert acct_file.exists()


def test_holdings_reconcile_hargreaves_is_read_only(client: TestClient, tmp_path: Path):
    account_file = tmp_path / "alice" / "isa.json"
    account_file.parent.mkdir(parents=True)
    original = {
        "owner": "alice",
        "account_type": "isa",
        "currency": "GBP",
        "holdings": [
            {"ticker": "AAA.L", "units": 8, "current_price_gbp": 1.4},
            {"ticker": "OLD.L", "units": 2, "current_price_gbp": 3},
            {"ticker": "CASH.GBP", "units": 100, "cost_basis_gbp": 100},
        ],
    }
    account_file.write_text(json.dumps(original, indent=2))
    broker_csv = (
        "Code,Stock,Units held,Price (pence),Cost (£)\n"
        "AAA,Alpha,10,150,15\n"
        "NEW,New holding,5,200,10\n"
        "CASH.GBP,Cash,110,100,110\n"
    )

    before = account_file.read_bytes()
    response = client.post(
        "/holdings/reconcile",
        data={"provider": "hargreaves", "owner": "alice", "account": "ISA"},
        files={"file": ("holdings.csv", broker_csv.encode(), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["added"] == [{"ticker": "NEW.L", "units": 5.0, "value_gbp": 10.0}]
    assert body["removed"] == [{"ticker": "OLD.L", "units": 2.0, "value_gbp": 6.0}]
    assert body["quantity_changed"] == [{"ticker": "AAA.L", "stored_units": 8.0, "imported_units": 10.0, "delta": 2.0}]
    assert body["value_changed"] == [
        {"ticker": "AAA.L", "stored_value_gbp": 11.2, "imported_value_gbp": 15.0, "delta_gbp": 3.8}
    ]
    assert body["cash_balance"] == {"stored_gbp": 100.0, "imported_gbp": 110.0, "delta_gbp": 10.0}
    assert account_file.read_bytes() == before
