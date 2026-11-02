"""POST /transactions/{id}/attribute-dividend: split a booked income sweep per holding (#10060).

Synthetic owner, tickers and amounts only.
"""

import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.importers import moneyhub

SWEEP = {
    "date": "2026-06-10",
    "settle_date": "2026-06-10",
    "currency": "GBP",
    "type": "DIVIDEND",
    "amount_minor": 2185,
    "comments": "Transfer from Income Account",
}
ESTIMATE = {
    "date": "2026-06-02",
    "type": "DIVIDEND",
    "ticker": "AAA.L",
    "amount_minor": 1500,
    "reason": "Automated dividend import",
    "estimated": True,
    "attribution_only": True,
}
LATER = {"date": "2026-07-01", "type": "DEPOSIT", "amount_minor": 10000}


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


def _seed(tmp_path, rows):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    path = owner_dir / "ISA_transactions.json"
    path.write_text(json.dumps({"owner": "alice", "account_type": "ISA", "transactions": rows}))
    return path


def _stored(path):
    return json.loads(path.read_text())["transactions"]


def _dividend_total(rows):
    return sum(r["amount_minor"] for r in rows if r["type"] == "DIVIDEND" and not r.get("attribution_only"))


def test_attribution_splits_the_sweep_per_holding_without_changing_the_total(tmp_path, monkeypatch):
    path = _seed(tmp_path, [ESTIMATE, SWEEP, LATER])
    client = _client(tmp_path, monkeypatch)
    before = _dividend_total(_stored(path))

    resp = client.post(
        "/transactions/alice:ISA:1/attribute-dividend",
        json={"parts": [{"ticker": "aaa.l", "amount_minor": 1500}, {"ticker": "BBB.L", "amount_minor": 600}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "attributed"
    assert [t["id"] for t in body["transactions"]] == ["alice:ISA:1", "alice:ISA:2", "alice:ISA:3"]
    stored = _stored(path)
    assert [(r.get("ticker"), r["amount_minor"], r.get("attributed_sweep", False)) for r in stored[1:4]] == [
        ("AAA.L", 1500, True),
        ("BBB.L", 600, True),
        (None, 85, False),
    ]
    assert stored[4] == LATER
    # Each pound is counted once: the total is unchanged, and the estimate the sweep
    # covered is still attribution-only rather than counted next to the AAA.L part.
    assert _dividend_total(stored) == before
    assert stored[0]["attribution_only"] is True

    divs = client.get("/dividends").json()
    attributed = {d["ticker"]: d for d in divs if d.get("attributed_sweep")}
    assert {t: d["amount_minor"] for t, d in attributed.items()} == {"AAA.L": 1500, "BBB.L": 600}


def test_attribution_refuses_a_row_that_is_not_a_booked_sweep(tmp_path, monkeypatch):
    path = _seed(tmp_path, [ESTIMATE, SWEEP])
    before = path.read_text()
    client = _client(tmp_path, monkeypatch)
    one_part = {"parts": [{"ticker": "AAA.L", "amount_minor": 1}]}

    assert client.post("/transactions/alice:ISA:0/attribute-dividend", json=one_part).status_code == 400
    too_much = {"parts": [{"ticker": "AAA.L", "amount_minor": 2186}]}
    assert client.post("/transactions/alice:ISA:1/attribute-dividend", json=too_much).status_code == 400
    assert client.post("/transactions/alice:ISA:9/attribute-dividend", json=one_part).status_code == 404
    assert client.post("/transactions/alice:ISA:1/attribute-dividend", json={"parts": []}).status_code == 422
    assert json.loads(path.read_text()) == json.loads(before)


def test_clients_cannot_set_the_attributed_flag(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "PFE",
        "date": "2024-05-01",
        "type": "DIVIDEND",
        "amount_minor": 500,
        "reason": "booked dividend",
        "attributed_sweep": True,
    }

    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text

    stored = _stored(tmp_path / "alice" / "isa_transactions.json")[0]
    assert "attributed_sweep" not in stored


def test_moneyhub_keeps_the_instrument_on_a_dividend_row():
    csv_data = (
        "Owner,Account,Date,Amount,Description,Category,Ticker\n"
        "alice,ISA,2026-06-10,21.85,Dividend,DIVIDEND,aaa.l\n"
        "alice,ISA,2026-06-11,-5.00,Fee,FEES,\n"
    )
    txs = moneyhub.parse(csv_data.encode("utf-8"))
    assert [t.ticker for t in txs] == ["AAA.L", None]
    by_symbol = moneyhub.parse(b"Owner,Account,Date,Amount,Category,Symbol\nalice,ISA,2026-06-10,1,DIVIDEND,BBB.L\n")
    assert by_symbol[0].ticker == "BBB.L"
