"""The "use current price as cost" estimate (#10095, part 2). Synthetic owners/tickers only."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.cost_basis_import import COST_ESTIMATE_REASON, plan_cost_estimate
from backend.common.holdings_rebuild import (
    COST_BASIS_ESTIMATE_DATE,
    COST_BASIS_ESTIMATE_SOURCE,
    COST_ESTIMATE_FLAG,
    rebuild_holdings_document,
)
from backend.config import config
from backend.routes import transactions

TODAY = date.today().isoformat()


def _estimate_row(units=10, price=2.0, day="2026-10-01", ticker="AAA.L"):
    return {
        "type": "TRANSFER_IN",
        "ticker": ticker,
        "date": day,
        "units": units,
        "price_gbp": price,
        COST_ESTIMATE_FLAG: True,
    }


def _rebuilt(transactions, holdings):
    doc = rebuild_holdings_document({"transactions": transactions}, "testowner", "isa", {"holdings": holdings})
    return {h["ticker"]: h for h in doc["holdings"]}


# ---- plan_cost_estimate ----------------------------------------------------


def test_plan_estimate_values_the_whole_holding_at_the_price_and_flags_it():
    rows, reason = plan_cost_estimate([], [{"ticker": "BP.", "units": 4}], "BP.L", 5.5, "2026-10-01")

    assert reason is None
    assert rows == [
        {
            "type": "TRANSFER_IN",
            "ticker": "BP.",
            "date": "2026-10-01",
            "units": 4.0,
            "price_gbp": 5.5,
            "reason": COST_ESTIMATE_REASON,
            COST_ESTIMATE_FLAG: True,
        }
    ]


def test_plan_estimate_refuses_a_holding_the_ledger_already_tracks():
    ledger = [{"type": "BUY", "ticker": "AAA.L", "date": "2020-01-01", "units": 10, "price_gbp": 1}]

    rows, reason = plan_cost_estimate(ledger, [{"ticker": "AAA.L", "units": 10}], "AAA.L", 2.0, TODAY)

    assert rows == []
    assert "already has transactions" in reason


@pytest.mark.parametrize(
    ("holdings", "expected"),
    [([], "no AAA.L holding in this account"), ([{"ticker": "AAA.L", "units": 0}], "AAA.L has no units held")],
)
def test_plan_estimate_refuses_a_missing_or_empty_holding(holdings, expected):
    assert plan_cost_estimate([], holdings, "AAA.L", 2.0, TODAY) == ([], expected)


# ---- holdings rebuild ------------------------------------------------------


def test_rebuild_tags_an_estimated_cost_and_keeps_acquired_date_unknown():
    held = _rebuilt([_estimate_row()], [{"ticker": "AAA.L", "units": 10, "cost_basis_gbp": 0}])

    holding = held["AAA.L"]
    assert (holding["units"], holding["cost_basis_gbp"]) == (10, 20.0)
    assert holding["cost_basis_source"] == COST_BASIS_ESTIMATE_SOURCE == "estimate"
    assert holding[COST_BASIS_ESTIMATE_DATE] == "2026-10-01"
    # An estimate says nothing about when the units were bought.
    assert "acquired_date" not in holding


def test_rebuild_keeps_a_known_acquired_date_under_an_estimate():
    held = _rebuilt([_estimate_row()], [{"ticker": "AAA.L", "units": 10, "acquired_date": "2015-05-05"}])

    assert held["AAA.L"]["acquired_date"] == "2015-05-05"


def test_rebuild_keeps_the_estimate_tag_when_a_real_purchase_is_added():
    buy = {"type": "BUY", "ticker": "AAA.L", "date": "2026-10-02", "units": 5, "price_gbp": 3.0}

    held = _rebuilt([_estimate_row(), buy], [{"ticker": "AAA.L", "units": 10}])

    holding = held["AAA.L"]
    assert (holding["units"], holding["cost_basis_gbp"]) == (15, 35.0)
    assert holding["cost_basis_source"] == "estimate", "part of the cost is still an estimate"
    assert holding["acquired_date"] == "2026-10-02"


def test_rebuild_clears_the_estimate_tag_once_the_estimated_units_are_sold():
    previous = [
        {"ticker": "AAA.L", "units": 10, "cost_basis_source": "estimate", COST_BASIS_ESTIMATE_DATE: "2026-10-01"}
    ]
    sell = {"type": "SELL", "ticker": "AAA.L", "date": "2026-10-03", "units": 10, "price_gbp": 2.2}
    buy = {"type": "BUY", "ticker": "AAA.L", "date": "2026-10-04", "units": 3, "price_gbp": 2.0}

    held = _rebuilt([_estimate_row(), sell, buy], previous)

    holding = held["AAA.L"]
    assert (holding["units"], holding["cost_basis_gbp"]) == (3, 6.0)
    assert "cost_basis_source" not in holding
    assert COST_BASIS_ESTIMATE_DATE not in holding


def test_rebuild_without_the_flag_is_a_recorded_cost():
    row = _estimate_row()
    del row[COST_ESTIMATE_FLAG]
    previous = [
        {"ticker": "AAA.L", "units": 10, "cost_basis_source": "estimate", COST_BASIS_ESTIMATE_DATE: "2026-10-01"}
    ]

    holding = _rebuilt([row], previous)["AAA.L"]

    assert "cost_basis_source" not in holding
    assert holding["acquired_date"] == "2026-10-01"


def test_rebuild_keeps_the_tag_on_an_estimated_cost_carried_forward():
    # Units of unknown cost: the previous (estimated) cost is carried forward, so its tag must be too.
    unpriced = {"type": "TRANSFER_IN", "ticker": "AAA.L", "date": "2026-10-01", "units": 10}
    previous = [
        {
            "ticker": "AAA.L",
            "units": 10,
            "cost_basis_gbp": 20.0,
            "cost_basis_source": "estimate",
            COST_BASIS_ESTIMATE_DATE: "2026-10-01",
        }
    ]

    holding = _rebuilt([unpriced], previous)["AAA.L"]

    assert holding["cost_basis_gbp"] == 20.0
    assert holding["cost_basis_source"] == "estimate"


# ---- POST /holdings/cost-basis/estimate ------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(transactions, "get_price_gbp", lambda ticker: {"AAA.L": 2.5}.get(ticker))
    return TestClient(create_app())


def _write_account(tmp_path, owner, account, holdings, ledger=None):
    owner_dir = tmp_path / owner
    owner_dir.mkdir(exist_ok=True)
    (owner_dir / f"{account}.json").write_text(
        json.dumps({"owner": owner, "account_type": account, "currency": "GBP", "holdings": holdings})
    )
    if ledger is not None:
        (owner_dir / f"{account}_transactions.json").write_text(json.dumps({"transactions": ledger}))


def _holding(tmp_path, owner, account, ticker):
    doc = json.loads((tmp_path / owner / f"{account}.json").read_text())
    return next(h for h in doc["holdings"] if h["ticker"] == ticker)


def _ledger(tmp_path, owner, account):
    path = tmp_path / owner / f"{account}_transactions.json"
    return json.loads(path.read_text())["transactions"] if path.exists() else []


def _post(client, ticker="AAA.L", **headers):
    body = {"owner": "testowner", "account": "ISA", "ticker": ticker}
    return client.post("/holdings/cost-basis/estimate", json=body, headers=headers)


def test_estimate_records_todays_price_as_an_estimated_cost(client, tmp_path):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 8, "cost_basis_gbp": 0}])

    resp = _post(client)

    assert resp.status_code == 200
    assert resp.json() == {
        "owner": "testowner",
        "account": "isa",
        "ticker": "AAA.L",
        "units": 8.0,
        "price_gbp": 2.5,
        "cost_basis_gbp": 20.0,
        "cost_basis_source": "estimate",
        "estimate_date": TODAY,
    }
    holding = _holding(tmp_path, "testowner", "isa", "AAA.L")
    assert (holding["units"], holding["cost_basis_gbp"]) == (8, 20.0)
    assert holding["cost_basis_source"] == "estimate"
    assert holding[COST_BASIS_ESTIMATE_DATE] == TODAY
    (row,) = _ledger(tmp_path, "testowner", "isa")
    assert row[COST_ESTIMATE_FLAG] is True
    assert row["reason"] == COST_ESTIMATE_REASON


def test_estimate_twice_is_refused_and_never_doubles_units(client, tmp_path):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 8}])
    assert _post(client).status_code == 200

    again = _post(client)

    assert again.status_code == 409
    assert "already has transactions" in again.json()["detail"]
    assert _holding(tmp_path, "testowner", "isa", "AAA.L")["units"] == 8
    assert len(_ledger(tmp_path, "testowner", "isa")) == 1


def test_estimate_without_a_current_price_writes_nothing(client, tmp_path):
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "ZZZ.L", "units": 8}])

    resp = _post(client, ticker="ZZZ.L")

    assert resp.status_code == 400
    assert "No current price" in resp.json()["detail"]
    assert _ledger(tmp_path, "testowner", "isa") == []


def test_estimate_checks_owner_access_before_writing(client, tmp_path, monkeypatch):
    from backend.common.errors import PermissionDeniedError

    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 8}])
    checked = []

    def deny(identity, owner, accounts_root=None):
        checked.append((identity, owner))
        raise PermissionDeniedError("nope")

    monkeypatch.setattr(transactions, "ensure_owner_access", deny)

    resp = _post(client)

    assert resp.status_code == 403
    assert checked == [(None, "testowner")]
    assert _ledger(tmp_path, "testowner", "isa") == []


def test_estimate_resolves_identity_with_the_owner_check_dependency(client, tmp_path, monkeypatch):
    """With disable_auth, get_owner_check_identity leaves the token unread (#11351), so a stale token is no 401."""
    monkeypatch.setattr(config, "disable_auth", True)
    _write_account(tmp_path, "testowner", "isa", [{"ticker": "AAA.L", "units": 8}])

    resp = _post(client, Authorization="Bearer not-a-real-token")

    assert resp.status_code == 200


def test_estimate_refuses_the_read_only_demo_store(client, monkeypatch):
    monkeypatch.setattr(
        transactions,
        "resolve_writable_store",
        lambda request: (transactions.LocalAccountsStore(root=None, is_global=True), transactions._RootResolution.NONE),
    )

    resp = _post(client)

    assert resp.status_code == 400


# ---- editing the estimate row ----------------------------------------------


def test_typing_a_new_price_over_an_estimate_makes_it_a_recorded_price():
    existing = {**_estimate_row(), "reason": COST_ESTIMATE_REASON}

    same = transactions._prepare_updated_transaction(existing, {"price_gbp": 2.0, "comments": "kept"})
    changed = transactions._prepare_updated_transaction(existing, {"price_gbp": 1.4})

    assert same[COST_ESTIMATE_FLAG] is True
    assert COST_ESTIMATE_FLAG not in changed


def test_create_and_import_bodies_cannot_set_the_estimate_flag():
    assert COST_ESTIMATE_FLAG in transactions._BOT_ONLY_FIELDS
