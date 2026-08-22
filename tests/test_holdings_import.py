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


@pytest.mark.parametrize(
    ("heading", "price", "expected"),
    [
        ("Price (pence)", "450", 4.5),
        ("Price (GBX)", "450", 4.5),
        ("Price (£)", "4.50", 4.5),
        ("Price (GBP)", "4.50", 4.5),
    ],
)
def test_hargreaves_parse_respects_price_units(heading, price, expected):
    csv_data = f"Code,Units held,{heading},Value (£),Cost (£)\nBP.,10,{price},45,30\n"

    [holding] = hargreaves.parse(csv_data.encode())

    assert holding.price == pytest.approx(expected)


@pytest.mark.parametrize(
    ("heading", "price"),
    [("Price (pence)", "4.50"), ("Price (£)", "450")],
)
def test_hargreaves_parse_corrects_price_scale_using_market_value(heading, price):
    """A contradictory HL heading must not inflate a holding by 100x (#6443)."""
    csv_data = f"Code,Units held,{heading},Value (£),Cost (£)\nBP.,10,{price},45,30\n"

    [holding] = hargreaves.parse(csv_data.encode())

    assert holding.price == pytest.approx(4.5)


def test_hargreaves_to_float_variants():
    # None or blank strings should resolve to ``None`` without raising.
    assert hargreaves._to_float(None) is None
    assert hargreaves._to_float("   ") is None

    # Comma separated numbers should be normalised before conversion.
    assert hargreaves._to_float("1,234.56") == pytest.approx(1234.56)

    # Malformed numeric values should be ignored gracefully.
    assert hargreaves._to_float("not-a-number") is None


def test_first_number_skips_blank_first_column_for_valid_later_column():
    """A blank leading column must not shadow a valid later column (#6449)."""
    row = {"Price (pence)": "", "Price (GBX)": "450"}

    assert hargreaves._first_number(row, hargreaves._PENCE_PRICE_COLUMNS) == pytest.approx(450)


def test_hargreaves_parse_uses_later_price_column_when_first_is_blank():
    """An HL export with a blank ``Price (pence)`` but populated ``Price (GBX)``
    must still resolve the price rather than silently dropping it (#6449).
    """
    csv_data = "Code,Units held,Price (pence),Price (GBX),Cost (£)\nBP.,10,,450,30\n"

    [holding] = hargreaves.parse(csv_data.encode())

    assert holding.price == pytest.approx(4.5)


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
    assert h["AAA.L"]["units"] == 10
    assert h["AAA.L"]["cost_basis_gbp"] == 15
    assert h["AAA.L"]["value_gbp"] == pytest.approx(15.0)
    assert Path(result["path"]).resolve() == acct_file.resolve()


def test_hargreaves_import_uses_persisted_foreign_ticker(monkeypatch):
    monkeypatch.setattr(
        update_holdings_from_csv,
        "resolve_instrument_ticker",
        lambda ticker: "MSFT.US" if ticker == "MSFT" else None,
    )

    assert update_holdings_from_csv._normalise_ticker("MSFT", "hargreaves") == "MSFT.US"
    assert update_holdings_from_csv._normalise_ticker("3IN", "hargreaves") == "3IN.L"


def test_hargreaves_import_warns_when_falling_back_to_l_suffix(monkeypatch, caplog):
    """An unresolvable bare ticker must still fall back to .L (CSV import can't
    block on a live lookup) but should log so it can be reconciled later (#6310)."""
    monkeypatch.setattr(update_holdings_from_csv, "resolve_instrument_ticker", lambda ticker: None)

    with caplog.at_level("WARNING", logger=update_holdings_from_csv.logger.name):
        result = update_holdings_from_csv._normalise_ticker("3IN", "hargreaves")

    assert result == "3IN.L"
    assert any("3IN" in record.getMessage() for record in caplog.records)


def test_update_holdings_from_csv_aggregates_duplicate_ticker_rows(tmp_path: Path, monkeypatch):
    """Two CSV rows for the same ticker must collapse into one holding (#6264)."""
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    csv_data = "Code,Stock,Units held,Price (pence),Cost (£)\n" "AAA,Alpha,10,150,15\n" "AAA,Alpha,5,150,7.5\n"
    update_holdings_from_csv.update_from_csv(
        owner="alice", account="isa", provider="hargreaves", data=csv_data.encode()
    )
    data = json.loads((tmp_path / "alice" / "isa.json").read_text())
    assert len(data["holdings"]) == 1
    holding = data["holdings"][0]
    assert holding["ticker"] == "AAA.L"
    assert holding["units"] == pytest.approx(15.0)
    assert holding["cost_basis_gbp"] == pytest.approx(22.5)
    assert holding["value_gbp"] == pytest.approx(22.5)


def test_update_holdings_from_csv_merges_into_existing_document(tmp_path: Path, monkeypatch):
    """Fields already on the stored document must survive a CSV import (#6264)."""
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    acct_dir = tmp_path / "alice"
    acct_dir.mkdir(parents=True)
    existing = {
        "owner": "alice",
        "account_type": "isa",
        "currency": "GBP",
        "last_updated": "2020-01-01",
        "holdings": [{"ticker": "OLD.L", "units": 1, "value_gbp": 1, "cost_basis_gbp": 1}],
        "notes": "keep me",
    }
    (acct_dir / "isa.json").write_text(json.dumps(existing))

    update_holdings_from_csv.update_from_csv(
        owner="alice", account="isa", provider="hargreaves", data=SAMPLE_CSV.encode()
    )

    data = json.loads((acct_dir / "isa.json").read_text())
    assert data["notes"] == "keep me"
    assert {h["ticker"] for h in data["holdings"]} == {"AAA.L", "BBB.L"}
    assert data["last_updated"] != "2020-01-01"


def test_update_from_csv_is_not_clobbered_by_stale_transactions_file(tmp_path: Path, monkeypatch):
    """Regression test for #6263: importing a CSV must not be silently
    overwritten by a rebuild from an unrelated, stale ``*_transactions.json``
    ledger for the same account.
    """
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir(parents=True)
    stale_tx = {
        "transactions": [
            {"type": "BUY", "ticker": "OLD", "units": 999, "date": "2020-01-01"},
        ]
    }
    (owner_dir / "isa_transactions.json").write_text(json.dumps(stale_tx))

    update_holdings_from_csv.update_from_csv(
        owner="alice",
        account="isa",
        provider="hargreaves",
        data=SAMPLE_CSV.encode(),
    )

    data = json.loads((owner_dir / "isa.json").read_text())
    tickers = {h["ticker"] for h in data["holdings"]}
    assert tickers == {"AAA.L", "BBB.L"}
    assert "OLD" not in tickers


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
