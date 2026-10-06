import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import importers
from backend.app import create_app
from backend.config import config
from backend.importers import moneyhub
from backend.routes.transactions import Transaction
from backend.timeseries import cache as timeseries_cache

MONEYHUB_SAMPLE = Path(__file__).parent / "data" / "moneyhub_sample.csv"


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    app = create_app()
    return TestClient(app)


def test_import_transactions_full_featured_row(tmp_path, monkeypatch):
    """A parsed row with price/units/fees/comments/reason_to_buy set must have
    every field persisted and coalesced correctly (price -> price_gbp,
    reason_to_buy -> reason). Provider-agnostic: builds the parsed
    ``Transaction`` directly and stubs ``importers.parse`` rather than relying
    on a specific provider's CSV parser.
    """
    client = _make_client(tmp_path, monkeypatch)
    row = Transaction(
        owner="alice",
        account="ISA",
        date="2024-05-01",
        ticker="PFE",
        type="BUY",
        price=10.5,
        units=2,
        fees=1.0,
        comments="test",
        reason_to_buy="diversify",
    )
    monkeypatch.setattr(importers, "parse", lambda provider, data: [row])

    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves"},
        files={"file": ("tx.csv", b"unused", "text/csv")},
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
    assert persisted["id"] == "alice:isa:0"


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
    assert persisted["account"] == "isa"
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


def test_moneyhub_parse_header_only_csv_returns_no_transactions():
    """Header-only CSV (all required columns, zero data rows) parses to []."""
    csv_data = "Id,Owner,Account,Date,Amount,Description,Category\n"
    assert moneyhub.parse(csv_data.encode("utf-8")) == []


def test_moneyhub_parse_row_with_empty_date_has_no_composite_key():
    csv_data = "Owner,Account,Date,Amount,Description,Category\n" "alice,Current,,-42.50,Tesco Store,Groceries\n"

    transactions = moneyhub.parse(csv_data.encode("utf-8"))

    assert len(transactions) == 1
    assert transactions[0].date == ""
    assert transactions[0].external_id is None


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


def _fake_fx_history(rates_by_day):
    """Stand-in for ``load_fx_history`` that honours its ``start``/``end`` window."""
    calls = []

    def load(curr, start=None, end=None):
        calls.append((curr, start, end))
        rows = [
            (pd.Timestamp(day), rate)
            for day, rate in rates_by_day.get(curr, {}).items()
            if (start is None or date.fromisoformat(day) >= start) and (end is None or date.fromisoformat(day) <= end)
        ]
        return pd.DataFrame(rows, columns=["Date", "Rate"])

    load.calls = calls
    return load


def _post_rows(client, monkeypatch, rows):
    monkeypatch.setattr(importers, "parse", lambda provider, data: rows)
    resp = client.post(
        "/transactions/import",
        data={"provider": "hargreaves"},
        files={"file": ("tx.csv", b"unused", "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()


def _usd_row(**overrides):
    fields = {
        "owner": "alice",
        "account": "ISA",
        "date": "2024-05-04",
        "ticker": "MSFT",
        "type": "BUY",
        "currency": "USD",
        "price": 100.0,
        "units": 2,
    }
    return Transaction(**{**fields, **overrides})


def test_import_converts_non_gbp_price_at_trade_date_rate(tmp_path, monkeypatch):
    """A USD price is converted with the stored rate for the trade date, not stored as GBP (#9679).

    2024-05-04 is a Saturday: the Friday fixing applies, never the later rate.
    """
    client = _make_client(tmp_path, monkeypatch)
    fx = _fake_fx_history({"USD": {"2024-05-02": 0.79, "2024-05-03": 0.8, "2024-05-07": 0.9}})
    monkeypatch.setattr(timeseries_cache, "load_fx_history", fx)

    data = _post_rows(client, monkeypatch, [_usd_row()])

    assert data["skipped"] == []
    [persisted] = data["persisted"]
    assert persisted["price_gbp"] == pytest.approx(80.0)
    assert persisted["price"] == pytest.approx(100.0)
    assert persisted["currency"] == "USD"
    assert fx.calls and all(curr == "USD" and end == date(2024, 5, 4) for curr, _start, end in fx.calls)
    stored = json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())
    assert stored["transactions"][0]["price_gbp"] == pytest.approx(80.0)


@pytest.mark.parametrize(
    ("rates", "row_overrides"),
    [
        ({}, {}),
        ({"USD": {"2024-04-20": 0.8}}, {}),
        ({"USD": {"2024-05-03": 0.8}}, {"date": None}),
    ],
    ids=["no-fx-history", "no-rate-near-trade-date", "undated-row"],
)
def test_import_rejects_non_gbp_price_without_trade_date_rate(tmp_path, monkeypatch, rates, row_overrides):
    """No stored trade-date rate means the row is rejected, never stored at a guessed rate (#9679)."""
    client = _make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(timeseries_cache, "load_fx_history", _fake_fx_history(rates))
    gbp_row = Transaction(owner="alice", account="ISA", date="2024-05-04", ticker="PFE", price=10.5, units=1)

    data = _post_rows(client, monkeypatch, [_usd_row(**row_overrides), gbp_row])

    assert [row["ticker"] for row in data["persisted"]] == ["PFE"]
    [skipped] = data["skipped"]
    assert skipped["ticker"] == "MSFT"
    assert "USD" in skipped["skip_reason"]
    assert "FX" in skipped["skip_reason"]


@pytest.mark.parametrize("currency", ["GBP", "gbp", None, "", "GBX", "GBp"])
def test_import_gbp_or_absent_currency_copies_price_unchanged(tmp_path, monkeypatch, currency):
    """GBP, already-scaled pence and absent currencies keep ``price_gbp == price`` with no FX lookup."""
    client = _make_client(tmp_path, monkeypatch)

    def no_fx(*_args, **_kwargs):
        raise AssertionError("GBP rows must not consult FX history")

    monkeypatch.setattr(timeseries_cache, "load_fx_history", no_fx)
    row = Transaction(owner="alice", account="ISA", date="2024-05-01", ticker="PFE", price=10.5, units=2)
    row.currency = currency

    data = _post_rows(client, monkeypatch, [row])

    [persisted] = data["persisted"]
    assert persisted["price_gbp"] == 10.5
    assert "price" not in persisted


def test_import_non_gbp_row_with_explicit_price_gbp_needs_no_fx(tmp_path, monkeypatch):
    """An importer that already supplied ``price_gbp`` is trusted as-is; only the conflict check applies."""
    client = _make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(timeseries_cache, "load_fx_history", _fake_fx_history({}))

    data = _post_rows(client, monkeypatch, [_usd_row(price=None, price_gbp=80.0)])

    [persisted] = data["persisted"]
    assert persisted["price_gbp"] == 80.0
